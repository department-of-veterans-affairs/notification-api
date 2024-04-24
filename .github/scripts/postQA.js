// File: .github/scripts/postQA.js
// Purpose: Post a QA summary based on labels in a pull request.

const { getLatestReleaseTag, bumpVersion, getUpdateType } = require('../../src/versionUtils');

module.exports = async ({github, context, core}) => {
  try {
    const prNumber = context.issue.number;
    const {data: pr} = await github.rest.pulls.get({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: prNumber
    });

    // const labels = pr.labels.map(label => label.name).join(", ");

    // Utilize versionUtils.js to get the latest release tag and prepare version bump
    const latestTag = await getLatestReleaseTag(github, context);
    const { newVersion, updateType } = bumpVersion(labels, versionParts);

    // Prepare summary content with version details
    // const commentBody = `### QA Summary\n- PR labels: ${labels}\n- Please review the labels and ensure they match the QA requirements.`;
    const summaryContent = `
### Update Details
- Latest Version: ${latestTag}
- New Version: ${newVersion} (${updateType} update)
- PR labels: ${labels}
    `;
    require('fs').appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);

    core.setOutput("summary-posted", "true");
  } catch (error) {
    core.setFailed(`Failed to post QA summary: ${error.message}`);
  }
};

