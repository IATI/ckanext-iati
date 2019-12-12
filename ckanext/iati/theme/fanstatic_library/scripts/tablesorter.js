// Table sorter module
this.ckan.module('table-sorter', function (jQuery, _) {
  return {
    options: {
    },

    initialize: function () {
      var self = this;
      this.el.ready(function(){
          self._onReady(self.el);
     });
    },

    _onReady: function(el) {
      el.tablesorter({sortList: [[0,0]]});
   }
 }
});
