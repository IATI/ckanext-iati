#!/usr/bin/env node

// This file is only used to generate the iati.css within
// fanstatic_library/styles and is for use if the less sheets need updating.
// NOTE: Please see setup.sh for information on setting yourself up

var path = require('path');
var watchr = require('watchr');
var exec = require('child_process').exec;
var watch = path.join(__dirname, 'less');

function now() {
  return new Date().toISOString().replace('T', ' ').substr(0, 19);
}

function compile(type, path) {
  var start = Date.now();
  // var sheet = path.replace(watch, '').split('/')[1].replace('.less', '');
  // var filename = sheet + '.css';
  var input = __dirname + '/less/iati.less';
  var output = __dirname + '/fanstatic_library/styles/iati.css';
  exec(
    '`npm bin`/lessc ' + input + ' > ' + output,
    function (err, stdout, stderr) {
      var duration = Date.now() - start;
      if (err) {
        console.log('An error occurred running the less command:');
        console.log(err.message);
      } else if (stderr || stdout) {
        console.log(stdout, stderr);
      } else {
        console.log('[%s] recompiled in %sms', now(), duration);
      }
    }
  );
}

console.log('Watching %s', watch);
watchr.watch({
  paths: watch,
  listeners: { change: compile }
});
compile();
