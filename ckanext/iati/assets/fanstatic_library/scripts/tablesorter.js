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
      var given_order = $("#field-order-by").val();
      console.log(given_order);
      if (given_order == "name asc" || given_order == "title asc"){
          // Ascending order
          el.tablesorter({sortList: [[0,0]]});
      }else if (given_order === "name desc" || given_order === "title desc"){
          // Descending order
	  el.tablesorter({sortList: [[0,1]]});
      }else{
         // This is default order
         el.tablesorter({sortList: [[0,0]]});
      }}
 }
});
