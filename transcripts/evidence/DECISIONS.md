# DECISIONS

Rules and choices that every later session must respect. Add new decisions at the end.

1. The agent is an editor. It never writes new lines or poems on its own.
2. The agent may suggest changes in `feedback/`. It edits a poem only when the owner approves that specific change.
3. Keep the style spare. Do not add explanations to poems.
4. Never rewrite a line that has been marked final.
5. Read PROJECT_STATE and DECISIONS before anything else.
6. (Session 2, 2026-10-15) The owner approved exactly one change: in poems/harbor-lantern.md, "its light a slow and patient tide." became "its light a patient tide." (a cut, no new words). It was applied with str_replace. The approval covers only that line. The other suggestions in feedback/editor-note-lantern-light.md (winter-bread line 4, paper-moths line 6, motif question) remain unapproved and must not be edited without separate owner approval.
