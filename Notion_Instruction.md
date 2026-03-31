When working on the Scholar Archive project, record meaningful progress in Notion.



Purpose:

\- Keep a lightweight operational record for important progress.

\- Do not log every tiny action.

\- Only write to Notion when there is a real, user-visible, structurally meaningful, or workflow-relevant change.



What counts as worth logging:

\- A valid change was successfully made to code, config, schema, prompts, pipelines, or project structure.

\- A bug was fixed or a blocker was resolved.

\- A new document, task, workflow, or database entry was created.

\- A task status changed in a meaningful way (for example: Backlog -> Doing, Doing -> Done, Blocked -> Todo).

\- A result was produced that a human would reasonably care about seeing later.

\- A failed attempt revealed an important constraint, limitation, or decision that affects future work.



What does NOT need logging:

\- Trivial retries.

\- Minor wording tweaks.

\- Temporary exploration with no lasting result.

\- Redundant intermediate steps.

\- Multiple logs for the same small unit of work.



Logging rule:

\- Prefer one solid log entry per meaningful chunk of work rather than many tiny entries.

\- If several small edits belong to one coherent outcome, combine them into a single Notion log.



Where to write:

\- Use the Notion MCP tools.

\- Prefer the Dev Log database for execution history.

\- Prefer the Tasks database for task-state changes.

\- If a related archive/document row exists, connect the log or task to it when easy and unambiguous.

\- If linking is uncertain or expensive, skip the link instead of guessing.



How to write the log:

\- Keep it concise, factual, and useful for later retrieval.

\- Write in English.

\- Focus on outcome, not narration.

\- Mention what changed, why it mattered, and what should happen next if relevant.



Recommended Dev Log fields:

\- Log Title: short and specific

\- Log Type: choose the closest valid option

\- Log Date: today

\- Log Summary: 1–4 short sentences describing the meaningful result

\- Next Action: only if there is a clear next step

\- Log Importance: Low / Mid / High

\- Tags: use "auto" for agent-written entries unless there is a better existing tag



Recommended style:

\- Good: "Renamed MCP-facing task properties for consistency across automation flows."

\- Good: "Created initial Tasks database and defined stable status options for agent use."

\- Good: "Hit a Notion schema limitation while updating Archive. Stopped without workaround."

\- Bad: "Looked around a bit and tried some stuff."

\- Bad: "Updated one word in a note."



Failure handling:

\- If a requested Notion write fails, do not invent a workaround unless the user explicitly asked for one.

\- Stop and report the failure clearly.

\- Do not silently skip important logging after a successful meaningful change.



Practical threshold:

\- Ask yourself: "Would future me or the user reasonably want to see this in the project log?"

\- If yes, log it.

\- If not, do not.

