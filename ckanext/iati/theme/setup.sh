#!/bin/bash

# This is the front-end toolkit for devs wanting to work on the CSS/JS/Images
# of the ckanext-iati.
# REQUIRED: nodejs

# Installs less and nodewatch for the compiling of iati.css
npm install less@1.4.1 watchr@2.4.3
# Gets the dependancy manager bower (sudo might be required for this one, 
# because of the --global flag)
npm install --global bower@1.2.4
# Then installs bootstrap
bower install bootstrap#3.0.0 font-awesome#3.2.1
