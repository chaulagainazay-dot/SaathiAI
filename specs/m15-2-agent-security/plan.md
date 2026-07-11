# M15.2 Plan
saathi/security/redteam/{config,findings,targets,probes,runner,baseline,report,
hackagent,cli,api}.py; corpus security/redteam/attacks/corpus.yaml + targets.yaml;
tests test_m15_2_{security,harness}.py; report API /api/v1/security/redteam/*
(prod-disabled); critical manifest M15.2; baseline. Reuse M15/M15.1 boundaries;
do NOT weaken gateway/approval/isolation. Local commits only.
