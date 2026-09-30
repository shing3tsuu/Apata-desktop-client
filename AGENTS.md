# Task Management Rules

Before changing the project, read `TASKS.md` and consider every open task related to the current work.

## Workflow

1. The user defines the problem and the expected result.
2. The user and the agent discuss the implementation, constraints, and important details together.
3. After the approach is agreed upon, the agent adds the task to `TASKS.md` using the next available sequential number.
4. Adding a task to `TASKS.md` does not authorize implementation. Start writing code only after the user explicitly asks for it.
5. Follow the recorded task description during implementation. If the solution needs to change substantially, discuss it with the user first and then update the task.
6. After implementation, verify the result with appropriate tests and static checks.
7. Change `closed` from `false` to `true` only after the task is fully implemented and verified.

## `TASKS.md` Format

Each task must contain:

- a sequential task number and a short title;
- a description of the required behavior and the agreed implementation;
- important constraints and actions that must not be taken;
- a `closed: true` or `closed: false` field.

Do not delete closed tasks or reuse their numbers. The file is a decision history for the project and must make it possible to restore lost context. If important implementation details appear while working, update the existing task instead of creating a duplicate.

## Project Language

Use English for all project content. This includes source code identifiers, docstrings, comments, exception messages, log messages, documentation, task descriptions, test names, and user-facing text unless the user explicitly requests another language for a specific item.

## Git Workflow

After a task is fully implemented and verified:

1. Update its entry in `TASKS.md` and set `closed: true`.
2. Review the working tree and stage only files that belong to that task.
3. Commit the changes in every affected repository with the exact message `Task <number> — <title>`.
4. Fetch the remote state and verify that the push will not overwrite unrelated history.
5. Push the task commits with a normal fast-forward push. Never force push unless the user explicitly requests it after reviewing the reason.

Keep different task numbers in separate commits whenever practical. When one task changes both the client and server, use the same task number and title in both repositories. Never use `git pull` blindly in a dirty working tree; fetch first and inspect any divergence before integrating it.
