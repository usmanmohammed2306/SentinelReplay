# Sentinel Replay - GitHub Learning and Contribution Workflow

Status: **BINDING SESSION-BASED WORKFLOW**  
Effective date: **2026-09-20**

GitHub activity begins in the **first implementation session**. Every completed learning brick should become a small, tested, understandable contribution. The goal is a consistently active profile backed by meaningful engineering progress, not an artificially filled contribution graph.

## 1. First-session setup

Before the first pushed commit:

1. Create Sentinel Replay as a standalone repository, not a fork.
2. Use `main` as the default branch.
3. Confirm the local commit author name.
4. Confirm the repository commit email is associated with the user's GitHub account, or use the GitHub-provided `noreply` address.
5. Bootstrap `main` with the reviewed planning baseline **and the already-tested local foundation preview**, add the GitHub repository as `origin`, and push it. Do not pretend existing code was created on later dates.
6. Make one genuinely new S01 improvement or test on a short-lived branch, open its pull request, and merge it into `main` after CI and teach-back.
7. Confirm both the bootstrap commit and first code pull request are attributed to the correct GitHub profile.

The reviewed initial import is the only direct-to-`main` bootstrap exception. All subsequent implementation bricks use pull requests.

Repository visibility:

- Public is preferred for portfolio visibility once no secret or personal information is present.
- A private repository is acceptable during early work, but private contribution visibility must be enabled if the user wants the activity count displayed publicly.
- Visibility changes are a user decision and are never made silently.
- If the repository begins private, enable private-contribution visibility when the user wants its contribution count displayed; choose a license before changing the repository to public.

## 2. Contribution cycle

For each brick:

```text
read STATUS and previous lab note
        -> create short-lived branch
        -> write or inspect failing test
        -> implement smallest behavior
        -> run focused and regression tests
        -> inspect real output
        -> complete student variation and teach-back
        -> update lab note and STATUS
        -> commit coherent changes
        -> push branch
        -> open focused pull request
        -> CI passes
        -> self-review changed files
        -> merge into main when the complete slice passes
        -> verify remote main and contribution attribution
```

Work on a non-default branch is valuable, but it is not considered published until it is merged into `main`.

## 3. Branch naming

Use the stable task ID and a short purpose:

```text
learn/s01-python-smoke-test
learn/s02-canonical-json
learn/s03-journal-chain
fix/s13-symlink-escape
docs/s25-provenance-report
```

Branches are short lived. A normal branch contains one accepted slice and is removed after merge. A difficult slice may span several sessions; coherent progress commits may be pushed to its branch without pretending the slice is finished.

## 4. Commit standard

Prefer one to three meaningful commits per brick. Examples:

```text
test(contracts): specify canonical map ordering
feat(contracts): add domain-separated canonical hashing
docs(learning): record canonicalization lab results
```

Each commit should:

- compile or intentionally contain a clearly identified failing test during local development;
- describe one coherent change;
- avoid unrelated formatting churn;
- preserve authorship attribution;
- never contain secrets, credentials, raw incident data, `.env` files, or generated dependency directories.

Do not create:

- empty commits solely for a green square;
- retroactively backdated commits;
- dozens of tiny commits that split one idea artificially;
- commits containing only generated noise;
- commits that bypass tests simply to manufacture activity.

A missed contribution date is preferable to a dishonest contribution.

## 5. Pull request standard

Every brick PR contains:

```text
Task ID:
Concept learned:
Invariant:
Failure demonstrated:
Implementation summary:
Tests run:
Observed result:
Student variation:
Limitations:
Lab note:
Next brick:
```

Keep the PR small enough to review in one sitting. The self-review must inspect the actual diff, not only the green CI badge.

## 6. Merge strategy

Default strategy: **squash merge one completed brick into `main`**. For a multi-session slice, a normal merge is allowed when preserving several coherent, passing learning commits materially improves the history.

Reasons:

- each brick becomes one understandable default-branch unit;
- unfinished intermediate commits do not clutter the permanent history;
- the PR preserves discussion and detailed development context;
- the default branch remains continuously runnable.

Use a normal merge only when preserving a multi-commit history teaches something important. Do not force-push `main` or rewrite published release history.

## 7. Contribution visibility rules

GitHub currently attributes commit contributions when:

- the commit email is associated with the GitHub account or is the correct GitHub `noreply` address;
- the repository is standalone rather than merely a fork;
- the commit is present on the repository's default branch or `gh-pages`;
- the account has the required relationship to the repository.

Contribution display can take time to update. If a commit is missing:

1. verify the author email with `git log`;
2. confirm the email is associated with the GitHub account;
3. confirm the commit reached `main`;
4. confirm the repository is not a fork;
5. wait up to 24 hours before treating the display as broken.

The authoritative current reference is GitHub's Profile Contributions documentation: <https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference>.

## 8. Sustainable GitHub rhythm

- Work in focused sessions on the active slice; do not start a second slice to manufacture activity.
- Push coherent progress to the slice branch when it is safe and useful for backup or review.
- Merge only when the slice definition of done passes; a quiet contribution date is preferable to a false completion.
- Publish a stage report and development tag only after its evidence gate passes, such as `stage-01-complete`.
- Update README screenshots and public claims only when they reflect working behavior.
- Reforecast duration at each stage gate from observed throughput and named risks.

Four to five meaningful work sessions per week is a sustainable default, not a deadline or contribution quota. Faster or slower progress is acceptable when the evidence remains honest.

## 9. GitHub planning artifacts

Use GitHub features only when they improve learning or traceability:

- one milestone per project stage;
- one issue per slice or substantial sub-brick;
- labels such as `learning`, `recorder`, `replay`, `provenance`, `policy`, `security`, `frontend`, and `benchmark`;
- pull requests linked to their task issue;
- releases only at meaningful gates.

Do not create dozens of placeholder issues merely to generate activity.

## 10. Portfolio quality standard

A recruiter should see:

- steady progress over time;
- small, comprehensible pull requests;
- tests evolving with the implementation;
- architectural decisions documented before complexity accumulates;
- benchmark reports backed by commands;
- honest limitations and conformance claims;
- a clean default branch that can be run at every completed stage gate.

The green graph is a side effect of disciplined construction. The repository history itself is the stronger portfolio signal.
