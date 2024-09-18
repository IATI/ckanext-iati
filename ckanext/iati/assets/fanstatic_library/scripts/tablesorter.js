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
          el.tablesorter({sortList: [[0,0]]});
      } else if (given_order === "name desc" || given_order === "title desc"){
        el.tablesorter({sortList: [[0,1]]});
      } else if (given_order === "publisher_iati_id asc"){
        console.log('publisher_iati_id asc')
        el.tablesorter({sortList: [[1,0]]});
      } else if (given_order === "publisher_iati_id desc"){
        console.log('publisher_iati_id desc')
        el.tablesorter({sortList: [[1,1]]});
      } else if (given_order === "publisher_organization_type asc"){
        el.tablesorter({sortList: [[2,0]]});
      } else if (given_order === "publisher_organization_type desc"){
        el.tablesorter({sortList: [[2,1]]});
      } else if (given_order === "publisher_country asc"){
        el.tablesorter({sortList: [[3,0]]});
      } else if (given_order === "publisher_country desc"){
        el.tablesorter({sortList: [[3,1]]});
      } else if (given_order === "created asc"){
        el.tablesorter({sortList: [[5,0]]});
      } else if (given_order === "created desc"){
        el.tablesorter({sortList: [[5,1]]});
      } else{
        el.tablesorter({sortList: [[0,0]]});
      }}
 }
});
