// createReleaseNotes.js

async function createReleaseNotes(params) {
  const { github, context, core } = params;

  try {
    // Log the entire inputs object to the GitHub Actions summary
    core.summary.addRaw(`Inputs received: ${JSON.stringify(process.inputs)}`).write();

    // Retrieve the previous version from the inputs
    // const previousVersion = context.inputs.PREVIOUS_VERSION;

    // Output the previous version to the console
    console.log(`The previous release version was: ${previousVersion}`);
  } catch (error) {
    core.setFailed(`Failed to generate summary: ${error.message}`);
    console.error(error);
  }
}

module.exports = createReleaseNotes;

