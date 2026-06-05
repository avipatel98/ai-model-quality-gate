# K6 Analysis

## Ramp-Up Results

The ramp-up scenario increased traffic to 50 virtual users and completed 7,282 requests at an average of 24.25 requests per second. The p95 response time was 18.54 ms and the p95 waiting time was 18.51 ms, both far below the configured thresholds. The error rate stayed at 0%, so the API did not hit a visible capacity ceiling during this run. The main conclusion is that the TF-IDF classifier is lightweight enough for local inference at this level of concurrency; response time stayed stable as load increased.

## Spike Results

The spike scenario jumped to 100 virtual users and completed 6,717 requests at an average of 55.64 requests per second. The p95 response time was 25.69 ms and the p95 waiting time was 25.68 ms, again well under the limits. The error rate remained 0%, which shows the server recovered cleanly after the burst and did not produce 5xx errors or queue requests long enough to breach the SLA. This suggests the current API is suitable for the capstone load profile.
