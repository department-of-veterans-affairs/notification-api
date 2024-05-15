// createReleaseNotes.js
const { appendSummary, getReleaseVersionValue, logKeys } = require("./actionUtils");

// Function to format the current date for release title (e.g. 1.7.10 - 15 MAY 2024)
function formatDate() {
    const date = new Date();
    const options = { day: '2-digit', month: 'short', year: 'numeric' };
    return date.toLocaleDateString('en-US', options).toUpperCase();
}

// Create the Draft Release so as to append the release notes
async function createDraftRelease(github, owner, repo, tag_name) {
  try {
    const response = await github.rest.repos.createRelease({
      owner,
      repo,
      tag_name,
      name: `${tag_name} - ${formatDate()}`,
      draft: true,
      prerelease: false
    });

    const releaseUrl = response.data.html_url; // Extract URL from the response object
    console.log('Release URL:', releaseUrl); // Log URL to the console
	// console.log('Release created successfully:', response);
    return releaseUrl; // Return the URL
  } catch (error) {
    console.error('Error creating release:', error);
  }
}

// Appends release notes based on previous tag
async function generateReleaseNotes(owner, repo, tag_name, previous_tag_name) {
  try {
	const response = await github.rest.repos.generateReleaseNotes({
      owner,
      repo,
      tag_name,
      // target_commitish: 'main',
      previous_tag_name,
      configuration_file_path: '.github/release.yaml',
    });

    console.log('Release notes generated successfully:', response);
    return response;
  } catch (error) {
    console.error('Error generating release notes:', error);
  }
}

async function createReleaseNotes(params) {
  const { github, context, core } = params;
  const { previousVersion } = process.env;
  const owner = context.repo.owner;
  const repo = context.repo.repo;

  try {
	// get currentVersion to create a release from that tag
	const currentVersion = await getReleaseVersionValue(github, owner, repo);

	// create release and return the url for the step summary
	const releaseUrl = await createDraftRelease(github, owner, repo, currentVersion)

	// append release notes based on the previousVersion
	const releaseNotes = await generateReleaseNotes(github, owner, repo, currentVersion, previousVersion);

	logKeys(releaseNotes.data);

	// Make a github summary that provides a link to the draft release and notifies of successful creation
	summaryContent = `
### Release Notes Created!
the release notes URL is ${releaseUrl}
Based on the previous version ${previousVersion}
And the update to ${currentVersion}
	`
	appendSummary(summaryContent)

    // Output the previous version to the console
    console.log(`The previous release version was: ${previousVersion}`);
  } catch (error) {
    core.setFailed(`Failed to generate summary: ${error.message}`);
    console.error(error);
  }
}

module.exports = createReleaseNotes;


    // Log the entire inputs object to the GitHub Actions summary
    // core.summary.addRaw(`Inputs received: ${JSON.stringify(process.inputs)}`).write();

