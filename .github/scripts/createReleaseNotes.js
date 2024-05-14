// createReleaseNotes.js


async function createReleaseNotes() {
  const { github, context, core } = params;
  const { previousVersion } = context.inputs.PREVIOUS_VERSION

  try {
	// Retrieve the previous version from the environment variables
	// const previousVersion = process.env.PREVIOUS_VERSION;

	// Output the previous version to the console
	console.log(`The previous release version was: ${previousVersion}`);
  } catch (error) {
	core.setFailed(`Failed to generate summary: ${error.message}`);
    console.error(error);
  }
} 

module.exports = createReleaseNotes;
