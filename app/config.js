// Where the apps look for wallpapers.
// LOCAL: the starter pack bundled inside the app.
// REMOTE: the catalog folder of the public repo. New wallpapers merged there show up in every
// installed app without an update. Set this after you publish the repo (see README).
window.IMPASTO_CONFIG = {
  localBase: 'catalog/',
  remoteBase: '', // e.g. 'https://raw.githubusercontent.com/<you>/impasto/main/catalog/'
  repoUrl: '', // e.g. 'https://github.com/<you>/impasto'
  version: '1.0.0',
};
