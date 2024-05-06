// prLabelSemver.js
const { prData } = require("./prData");
const fs = require("fs");

const prLabelSemver = async ({ github, context, core }) => {
  try {
    // Retrieve necessary data from prData.js
    const { label, prNumber, prUrl } = await prData({ github, context, core });

    // Determine the semver update type based on the label
    const semverValue = label.includes("breaking change")
      ? "MAJOR"
      : label.includes("hotfix") ||
          label.includes("security") ||
          label.includes("bug")
        ? "PATCH"
        : "MINOR";

    const summaryContent = `
### PR Label Semver Summary
- PR Number: [#${prNumber}](${prUrl})
- Label: ${label}
- Semver Bump: ${semverValue}
`;
    // Append the summary to the GitHub step summary file or log it
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    console.log("PR label and semver bump summary appended successfully.");
  } catch (error) {
    core.setFailed(
      `Failed to generate PR label semver summary: ${error.message}`,
    );
    console.error(error);
  }
};

module.exports = prLabelSemver;
