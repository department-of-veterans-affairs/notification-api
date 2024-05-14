// createReleaseNotes.js
const { appendSummary, getReleaseVersionValue } = require("./actionUtils");

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
	  // target_commitish: 'master',
	  name: `${tag_name} - ${formatDate()}`,
	  draft: true,
	  prerelease: false
	});
	console.log('Release created successfully:', response);
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
    return response; // You can return this if you need to use the response outside this function
	// return response.data
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
	// get currentVersion to compare with previousVersion for release notes
	const currentVersion = await getReleaseVersionValue(github, owner, repo);
	const createRelease = await createDraftRelease(github, owner, repo, tag_name)
	const releaseNotes = await generateReleaseNotes(github, owner, repo, tag_name, previousVersion);

	// Make a github summary that provides a link to the draft release and notifies of successful creation

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

