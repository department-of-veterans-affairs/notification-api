// File: .github/scripts/postQA.js
const fs = require('fs');
const prData = require('./prData');

async function generatePRSummary({ github, context, core }) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const name = "RELEASE_VERSION"

  currentVersion = github.rest.actions.getRepoVariable({
	owner,
	repo,
	name,
  });

  console.log(currentVersion)


  // try {
    // const org = 'department-of-veterans-affairs'; // replace with your organization name or pass as a parameter

    // const permissions = await github.rest.actions.getActionsPermissionsOrganization({
      // org: org,
    // });

    // console.log(permissions);
  // } catch (error) {
    // console.error('Failed to retrieve permissions:', error);
  // }


  // pritn out the variable value for RELEASE_VERSION so I can use its value in prData.js
  // Log all environment variables (this proved not effective)
  // console.log('Available Environment Variables:', process.env);


  // console.log the VARS from the context!
  // const contextStringified = JSON.stringify(github.context, null, 2);
  // console.log("Stringified Context:", contextStringified);

  const permissions = github.rest.actions.getGithubActionsDefaultWorkflowPermissionsOrganization({
  org,
});

  // console.log(context.vars)
  console.log(permissions)







  // Fetch repository secrets
  // const owner = process.env.GITHUB_REPOSITORY_OWNER;
  // const repo = process.env.GITHUB_REPOSITORY.split('/')[1];

  // try {
    // const response = await github.rest.actions.listRepoSecrets({
      // owner,
      // repo
    // });

    // // Check if RELEASE_VERSION is among the secrets
    // const secrets = response.data.secrets;

    // const releaseVersion = secrets.find(secret => secret.name === 'RELEASE_VERSION');

    // if (releaseVersion) {
      // console.log('RELEASE_VERSION is available as a repo secret.');
    // } else {
      // console.log('RELEASE_VERSION is not available as a repo secret.');
    // }
  // } catch (error) {
    // console.error('Failed to fetch repository secrets:', error);
  // }
  // // Need to get PR labels from the merge!  
  // // once I have this working I need to move it to prData.js
  // try {
    // const context = github.context;
    // if (context.eventName === 'push') {
      // console.log('Push event payload:', JSON.stringify(context.payload, null, 2));
    // } else {
      // console.log('Not a push event.');
    // }
  // } catch (error) {
    // console.error('Error logging payload:', error);
  // }

  // try {
    // // Retrieve necessary data from prData.js
    // const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });

    // // Determine the semver update type based on the label
    // const semverValue = label.includes('breaking change') ? 'MAJOR' :
                        // label.includes('hotfix') || label.includes('security') || label.includes('bug') ? 'PATCH' : 
                        // 'MINOR';

	// const allCapsLabel = label.toUpperCase();

    // // Assemble the message content
    // const summaryContent = `
// ### Update Details
// - PR Number: #${prNumber}
// - The PR label used for versioning is ${allCapsLabel}
// This will bump up from the previous release tag will be a ${semverValue} value
// This tag will not be created until a merge to the release branch. 
// - At the time of this message Release Branch SHA is: ${releaseBranchSha}
    // `;

    // // Append the summary to the GitHub step summary file
    // fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    // console.log('PR summary generated and appended successfully.');
  // } catch (error) {
    // core.setFailed(`Failed to generate PR summary: ${error.message}`);
    // console.error(error);
  // }
}

module.exports = { generatePRSummary };

