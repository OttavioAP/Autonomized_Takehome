start: 1:30 PM July 18th
1. first reading of rubric
2. git repo
3. create changelog,.env, gitignore, blueprints folder (for planning, specs, docs etc), readme, utils folder: everything I need regardless of stack
4. create list of features based on rubric. split based on two axis: MVP-non-MVP, functional vs non-functional
5. turned features.md into an explicit tracker, added claude.md instruction to always check it before work items, update after work items
6. planned more non-mvp requirements to avoid painting myself into a corner with tech stack selection or architectural choices
7. create timeline based on list of features
8. pick stack based on list of features
FastAPI: chosen based on familiarity, built in async (useful for I/O bound app), pydantic integration and the fact the recruiter mentioned it in a previous conversation.
Postgres: chosen based on familiarity, rdms support if the app ever needs multitenancy,rbac or more complex ui to support github/jira workflows as well as pgvector support.
HTMX: chosen due to my complete lack of experience with it, for its educational value.
9. 