var CKAN = CKAN || {}

CKAN.IATI = function($){
    return {
        openGroupDetails: function(){
            var div = $("#publisher-dialog");
            div.empty();
            div.html($("#publisher-info").html());
            div.dialog({
                "title": "About this publisher",
                "minWidth" : $("#container").width(),
                "height": $(window).height() * 0.6,
                "position": ["center","center"]
            });
            div.scrollTop(0);
        }
    }
}(jQuery)
