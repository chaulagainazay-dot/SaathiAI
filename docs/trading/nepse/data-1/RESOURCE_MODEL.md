# Resource model

After licensing, prefer bounded polling/daily pulls: one session status/index request, batched quotes at modest cadence, and daily bars through the existing dataset registry. No tick archive or always-on WebSocket is justified on the constrained host.
