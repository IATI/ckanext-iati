var CKAN = CKAN || {}

CKAN.IATI = function($){
    return {
        openGroupDetails: function(){
            var div = $("#publisher-dialog");
            div.empty();
            div.html($("#publisher-info").html());
            div.dialog({
                "minWidth" : $("#content").width(),
                "height": $(window).height() * 0.5,
                "position": ["center","center"]
            });
        }
    }
}(jQuery)
