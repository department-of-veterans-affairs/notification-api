// createReleaseNotes.js

async function createReleaseNotes(params) {
  const { github, context, core } = params;
  const { PREVIOUS_VERSION } = process.env;

  try {
    // Log the entire inputs object to the GitHub Actions summary
    core.summary.addRaw(`Inputs received: ${JSON.stringify(process.inputs)}`).write();

    // Output the previous version to the console
    console.log(`The previous release version was: ${PREVIOUS_VERSION}`);
  } catch (error) {
    core.setFailed(`Failed to generate summary: ${error.message}`);
    console.error(error);
  }
}

module.exports = createReleaseNotes;

