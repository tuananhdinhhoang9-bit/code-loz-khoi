# External skills — install selectively

Verified sources (2026-11-11):
- Google official skills: https://github.com/google/skills (index: https://github.com/google/skills/blob/main/index.json)
- OpenAI archived/deprecated catalog: https://github.com/openai/skills (the repo itself says it is deprecated; the particular skill below is still inspectable)
- Anthropic skills: https://github.com/anthropics/skills
- Installer reference: https://github.com/vercel-labs/skills/blob/main/docs/commands.md
- Codex skills doc: https://learn.chatgpt.com/docs/build-skills

## Prerequisite

Install Node.js with `npm`/`npx`. From **project root**, inspect the skill before installing. For stable projects pin upstream commits/versions after reviewing; never blindly install all community skills. The commands here use the upstream branch and thus may change over time.

## Recommended core skills (project-scoped)

```powershell
npx skills add google/skills --skill cloud-run-basics --skill cloud-sql-basics --skill google-cloud-storage-basics -a codex
npx skills add openai/skills --skill security-best-practices -a codex
npx skills add anthropics/skills --skill frontend-design -a codex
npx skills list
```

Source directories:

1. Cloud Run: https://github.com/google/skills/tree/main/skills/cloud/cloud-run-basics
2. Cloud SQL: https://github.com/google/skills/tree/main/skills/cloud/cloud-sql-basics
3. Cloud Storage: https://github.com/google/skills/tree/main/skills/cloud/google-cloud-storage-basics
4. Security: https://github.com/openai/skills/tree/main/skills/.curated/security-best-practices
5. UI: https://github.com/anthropics/skills/tree/main/skills/frontend-design

`security-best-practices` should be explicitly invoked at the security-review phase; it is not intended as an unconditional global rewrite skill. `frontend-design` matters for UI but should not override simplicity or assignment scope.

## Later only (Cloud Monitoring phase)

```powershell
npx skills add google/skills --skill cloud-run-alert-configuration -a codex
```

Source: https://github.com/google/skills/tree/main/skills/cloud/cloud-run-alert-configuration

## Optional if genuinely necessary

- Google Cloud Logging configuration: https://github.com/google/skills/tree/main/skills/cloud/cloud-logging-configuration-basics
- GCP Cloud Build basics: https://github.com/google/skills/tree/main/skills/cloud/cloud-build-basics (not needed if GitHub Actions handles builds)
- Browser testing `playwright`: https://github.com/openai/skills/tree/main/skills/.curated/playwright (original repo deprecated; local/manual browser testing is enough initially)

## Local skills already included

- `.agents/skills/student-simple-code/SKILL.md`: student-friendly code review.
- `.agents/skills/video-job-reliability/SKILL.md`: correct retry/failure demonstration.
- `.agents/skills/cloud-budget-guard/SKILL.md`: preflight against paid/destructive GCP actions.

Local skills are in the **repo**, so do not run a second external installer for them.
