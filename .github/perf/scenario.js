// k6 load scenario for the performance regression check in CI.
// The same script runs against the baseline and the candidate image; compare.py
// compares the "load" phase of both runs. Setup seeds a user and articles, so the
// measured requests are reads plus the authenticated current-user lookup.
import http from "k6/http";
import { check } from "k6";

const API = __ENV.API_URL || "http://localhost:8080/api";
const ARTICLES = 20;

export const options = {
  scenarios: {
    warmup: {
      exec: "warmup",
      executor: "constant-arrival-rate",
      rate: 10,
      timeUnit: "1s",
      duration: "10s",
      preAllocatedVUs: 10,
      tags: { phase: "warmup" },
    },
    load: {
      executor: "constant-arrival-rate",
      rate: 30,
      timeUnit: "1s",
      duration: "60s",
      startTime: "10s",
      preAllocatedVUs: 30,
      maxVUs: 60,
      tags: { phase: "load" },
    },
  },
  // Thresholds on the tagged sub-metrics make k6 export them in the summary.
  thresholds: {
    "http_req_duration{phase:load}": ["p(95)<5000"],
    "http_req_failed{phase:load}": ["rate<1"],
    "http_reqs{phase:load}": ["count>0"],
  },
};

// The app limits requests per client IP. A random X-Forwarded-For per request makes
// every request look like a different client (the app runs with
// --forwarded-allow-ips='*' in CI), so the limiter does not skew the measurement.
function clientHeaders(token) {
  const ip = `10.${rnd(256)}.${rnd(256)}.${rnd(256)}`;
  const headers = { "Content-Type": "application/json", "X-Forwarded-For": ip };
  if (token) {
    headers.Authorization = `Token ${token}`;
  }
  return { headers };
}

function rnd(max) {
  return Math.floor(Math.random() * max);
}

export function setup() {
  const suffix = Date.now();
  const user = {
    username: `perf${suffix}`,
    email: `perf${suffix}@example.com`,
    password: `perf-${suffix}-password`,
  };
  const registered = http.post(`${API}/users`, JSON.stringify({ user }), clientHeaders());
  if (registered.status !== 200) {
    throw new Error(`registration failed: ${registered.status} ${registered.body}`);
  }
  const token = registered.json("user.token");

  const slugs = [];
  for (let i = 0; i < ARTICLES; i++) {
    const article = {
      title: `Perf article ${i} ${suffix}`,
      description: "Seeded for the performance check",
      body: "Lorem ipsum ".repeat(50),
      tagList: ["perf", `tag${i % 5}`],
    };
    const created = http.post(
      `${API}/articles`,
      JSON.stringify({ article }),
      clientHeaders(token),
    );
    if (created.status !== 200) {
      throw new Error(`article creation failed: ${created.status} ${created.body}`);
    }
    slugs.push(created.json("article.slug"));
  }
  return { token, slugs };
}

export function warmup(data) {
  http.get(`${API}/articles?limit=20`, clientHeaders());
  http.get(`${API}/articles/${data.slugs[rnd(data.slugs.length)]}`, clientHeaders());
}

export default function (data) {
  const roll = rnd(10);
  let res;
  if (roll < 4) {
    res = http.get(`${API}/articles?limit=20`, clientHeaders());
  } else if (roll < 7) {
    res = http.get(`${API}/articles/${data.slugs[rnd(data.slugs.length)]}`, clientHeaders());
  } else if (roll < 9) {
    res = http.get(`${API}/tags`, clientHeaders());
  } else {
    res = http.get(`${API}/user`, clientHeaders(data.token));
  }
  check(res, { "status is 200": (r) => r.status === 200 });
}
