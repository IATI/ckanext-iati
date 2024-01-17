// Upload animation module
this.ckan.module('upload-animation', function (jQuery, _) {
  return {
    options: {
    },

    initialize: function () {
      var self = this;
      this.el.ready(function(){
          self.el.submit(function() {
            $('#submit').attr('disabled','disabled');
            $("#animation").show();
          })
      });
    }
  }
});
