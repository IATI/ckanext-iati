International Aid Transparency Initiative (IATI) Registry Extension for CKAN
============================================================================

Advice for contributing to the codebase.

Commit message style guide
--------------------------

`Chris Beams' advice on commit messages <http://chris.beams.io/posts/git-commit/>`_ should be followed.  The most important elements are summarised below.

Messages should be descriptive of the change contained within the commit, with the first line using the imperative mood, being capitalised and no more than 50 characters in length:

.. code::

   Refactor subsystem X for readability


If there is a corresponding issue, this should be referenced at the beginning of the message using square brackets and the issue number, preceded by a hash symbol.  The following example describes a commit that would be related to issue 15:

.. code::

    [#15] Update getting started documentation


Multiple issues can be referenced, listed in order of relevance. The following example describes a commit that would be most relevant to issue 22, but also issue 9:

.. code::

    [#22][#9] Fix broken link


Any subsequent lines should be wrapped at 72 characters. 
