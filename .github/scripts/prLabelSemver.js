// prLabelSemver.js
const { prData } = require("./prData");
const { appendSummary } = require("./actionUtils");

/**
 * Helper function to determine the semver update type based on the label list.
 *
 * @param {Array} labels - The list of labels of the pull request.
 * @returns {string} The semver value corresponding to the labels.
 */
function determineSemverValue(label) {
  if (labels.some(label => label.name.includes("breaking change"))) {
    return "MAJOR";
  }
  if (labels.some(label => ["hotfix", "security", "internal", "bug"].includes(label.name))) {
    return "PATCH";
  }
  return "MINOR";
}

/**
 * Automatically labels pull requests based on semantic versioning (semver) guidelines
 * and appends a summary to the GitHub action step.
 *
 * @param {object} params - The parameters containing github, context, and core objects.
 * @returns {Promise<void>} A Promise that resolves when the summary has been successfully appended,
 *                          or rejects if an error occurs during the operation.
 */
async function prLabelSemver(params) {
  const { github, context, core } = params;

  try {
    // Retrieve necessary data from prData.js
    const { label, prNumber, prUrl } = await prData({ github, context, core });

    // Determine the semver update type based on the labels
    const semverValue = determineSemverValue(label);

    // Construct the summary content
    const summaryContent = `
### PR Label Semver Summary
- PR Number: [#${prNumber}](${prUrl})
- Label: ${label}
- Semver Bump: ${semverValue}
`;
    // Append the summary to the GitHub step summary file or log it
    appendSummary(core, summaryContent);
  } catch (error) {
    core.setFailed(`Failed to generate summary: ${error.message}`);
    console.error(error);
  }
}

module.exports = prLabelSemver;

