google.load('visualization', '1', {'packages': ['geomap']});
google.setOnLoadCallback(drawMap);

function drawMap() {
   var data = new google.visualization.DataTable(iati_map_data);

   var options = {};
   options['dataMode'] = 'regions';
	 options['width'] = '640px';
	 options['showLegend'] = false;

   var container = document.getElementById('iati_map');
   var geomap = new google.visualization.GeoMap(container);
	 geomap.draw(data, options);
	 google.visualization.events.addListener(geomap, 'regionClick',function(e) { 
		  console.log(e);
	    location.href = "/package/search?country="+e.region; 
	  });
};