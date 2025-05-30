---
title: Contributor Guidelines
nav_order: 2
layout: default
parent: Development Guide
permalink: development-guide/contributor-guidelines
---


# Contributor Guidelines
{: .no_toc}

Please follow the following guidelines when contributing to RimSort.

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

## Basic Guidelines
1. Pull Requests need to be made AFTER all guidelines are met. It's OK to miss some stuff because we can catch it in review, but we should be proactive with docstrings, code formatting, etc. If not ready, use a draft.

2. Please submit Pull Requests which contain feature-specific changes only. PRs should not lump multiple changes into one thing. This so we can be more selective in discussion. This is a requirement, and deviation will cause PR to be closed.

3. Make sure your Pull Request passes the basic linter and Pytest checks before asking for a review. If they don't, they will be the first thing we ask you to fix.

4. There are GitHub Issue templates available on RimSort repository. Bug Reports and Feature Requests are to be submitted there, and if there is consensus on a request, it will become an "Implement ...." Issue. Please do not deviate from template and allow maintainers to modify the Issue to include relevant tasks and title information once consensus is reached.

   - Consensus = consensus between maintainers. That being said, we rely on your feedback, so you will have a say.
   - You are also welcome to fork this repository and make whatever changes you deem fit privately.

5. ALL PRs need to have a corresponding Issue and/or Issue sub-task(s) to reference. This is for transparency and overall will help anybody else helping to keep track of things.
   - Anybody can contribute to RimSort. That being said, we are a community and these guidelines will help encourage and enforce consistency with RimSort growth.
   - Maintainer or not - you do not have to be a maintainer to submit PR! Please don't hesitate to work from a fork or something if that's how you roll.

6. In 99% of situations, you should not submit pull requests that are only dependency bumps. Basic dependency bumps are handled automatically using dependabot.

## Versioning and Releases

We utilize automated semantic versioning based on a [GitHub action](https://github.com/PaulHatch/semantic-version/tree/v5.4.0/). This action will auto-increment the version based on keywords in commit messages, tags, and commits in general. The process is utilized by both the release and auto-build pipelines.

**Manual overrides using tags should be formatted with `v` as the prefix and follow the release format, e.g. `v1.1.1`.**

**SemVer will only monitor changes in specific directories for purposes of implicit types.** This is to ensure that changes to the repository that are irrelevant to the function of the code don't change the app version.

<details>
<summary> Currently monitored directories </summary>
  <ul>
    <li> app </li>
    <li> libs </li>
    <li> submodules </li>
    <li> themes </li>
  </ul>
</details>

### Release Description and Pipeline

|    Type    |                        Version Format                         | Trigger | Description                                                                                                                                      |
| :--------: | :-----------------------------------------------------------: | :-----: | :----------------------------------------------------------------------------------------------------------------------------------------------- |
|  Release   |                v\${major}.\${minor}.\${patch}                 | Manual  | Versions that can be safely used and are considered stable.                                                                                      |
|    Edge    | v\${major}.\${minor}.\${patch}-edge\${increment}+${short-sha} | Manual  | Versions that are released often and include the latest features and fixes, but may have significant breaking bugs in them.                      |
| Auto-Build | v\${major}.\${minor}.\${patch}-auto\${increment}+${short-sha} |  Auto   | Versions created by the auto-build pipeline triggered on every pull request and push to main. Not released. Builds created persist as artifacts. |

Releases are created through the manual triggering of the relevant GitHub workflow action. For safety, consider setting the release to only be created as a draft.

Edge releases will be overwritten, with a new edge tag created and the old release fully deleted. Stable releases will not be overwritten. By default, non-draft stable releases are protected, and the auto-action will fail if a release with the same version tag already exists.

If, for whatever reason, the build step completed, but the remaining steps of the release pipeline fails, you may re-run the workflow with an override to skip the build step by providing the action with the run ID of which it will grab the build artifacts from for release.

Beware that if a new commit was pushed to the target branch between the new release attempt and when the builds were actually made, there will be a commit mismatch between the builds and the release information. By default, the release pipeline will detect this and fail to maintain correct release info. **The version and version.xml in the build is always correct.**

### Versioning Keywords and Patterns

|   Type    |    Pattern     | Description                                                                                               |
| :-------: | :------------: | --------------------------------------------------------------------------------------------------------- |
|   major   |    (major)     | Major and breaking updates                                                                                |
|   minor   |    (minor)     | Minor updates. Not expected to be breaking, but may introduce new features and large amounts of bug fixes |
|   patch   | n/a (Implicit) | Non-breaking small changes. Incremented on PR if no other patterns.                                       |
| increment | n/a (Implicit) | Number of commits since last version change                                                               |
| short-sha | n/a (Implicit) | First seven characters of the commit sha identifier a build is made from                                  |

### Caveats and Potential Issues

#### Potential Race Condition

Due to how GitHub runner environments work, there is a potential race condition if a commit is made to the branch that the build and release action is running on. If something changes on the branch while the action is running, depending on what step the action is on, there may be differences in the version information in the release, and the commit being used for building. If especially unlucky where one runner for a specific build target loaded and checked out, but a commit is pushed to the branch before other runners for a different target, the builds created for the targets may all be on different commits.

**Note that the actual version.xml and subsequent app reported version will always be correct.**

To mitigate this issue, the version info for the release pipeline is grabbed first thing, before builds and testing has started. Additionally, a commit mismatch check is done just before release. If any of the artifact's target commits mismatch with the release commit, the workflow will fail by default.

## Developing Features

Please ensure if you have any feature request to check if there is already something planned. We are tracking features and issues related to RimSort in the GitHub repo's "Issues" tab. If it is not already in the issues tab, you can discuss this with maintainers first through the RimSort Discord server.

## Misc Coding Style

- The preferred Python formatter is: [ruff](https://docs.astral.sh/ruff/) (`pip install ruff`)
  - Here is the Ruff extension for [VS Code](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
  - Note that Ruff replaces isort, flake8 as well as black. If you have these, make sure to disable them to prevent conflicts.
- The preferred docstring format is: [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
- Type annotations should be added to function/method signatures.
  - Use Python 3.10+ standards. (Avoid importing Typing. [Pep604](https://peps.python.org/pep-0604/) instead of Optional)
- We use [mypy](https://mypy.readthedocs.io/en/stable/) for static type checking.
  - Grab [this extension](https://marketplace.visualstudio.com/items?itemName=matangover.mypy) for VS Code/VS Codium!
- For quick setup, you can install some of the dependencies described above along with additional modules for typing to automate your development:
  - `pip install -r requirements_develop.txt`
- VS Code workspace settings are included
- For shell scripts, we use [shfmt](https://github.com/mvdan/sh#shfmt)
  - [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=mkhl.shfmt)