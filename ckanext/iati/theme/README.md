
If you only want to get the latest theme, load the `iati_theme` plugin. 

To install the front-end toolkit for devs wanting to work on the CSS/JS/Images
of ckanext-iati follow these instructions:

1. Install node.js, eg https://github.com/joyent/node/wiki/Installing-Node.js-via-package-manager#ubuntu-mint-elementary-os

2. Cd to `./ckanext-iati/ckanext/iati/theme`

3. Chmod and run `./setup.sh`.

4. Run `node build.js`. This will watch for changes in less files and
   regenerate `iati.css`

