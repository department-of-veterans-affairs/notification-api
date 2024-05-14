// createReleaseNotes.js

// Retrieve the previous version from the environment variables
const previousVersion = process.env.PREVIOUS_VERSION;

// Output the previous version to the console
console.log(`The previous release version was: ${previousVersion}`);

module.exports = createReleaseNotes;
