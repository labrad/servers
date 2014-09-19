//$(".btn.btn").click(function(){
// $.ajax({type: "POST",
        // url: "http://localhost:8881/server_list/start",
        // data: {string},
        // success: function(data) {}
        // });
   // alert($( this ).attr("value"));
   // });
$(".btn.btn-primary").click(function(){
    $.ajax({type: "POST",
       url: "http://localhost:8881/server_list/start",
       data: {srv: $( this ).attr("value")},
       success: function(data) {}
      });
    //$("#<t:slot name='srvstart'/>").hide();
    //$("#loading").show();
    window.location.reload();
    // alert($( this ).attr("value"));
});

$(".btn.btn-danger").click(function(){
    $.ajax({type: "POST",
       url: "http://localhost:8881/server_list/stop",
       data: {srv: $( this ).attr("value")},
       success: function(data) {}
      });
    //$("#<t:slot name='srvstart'/>").hide();
    //$("#loading").show();
    window.location.reload();
    // alert($( this ).attr("value"));
});

//old crummy code:
//$("#<t:slot name='srvstart'/>").click(function(){
//$.ajax({type: "POST",
        // url: "http://localhost:8881/server_list/start",
        // data: {srv: $("#<t:slot name='srvname'/>").text()},
        // success: function(data) {}
        // });
    // $("#<t:slot name='srvstart'/>").hide();
    // $("#loading").show();
    // window.location.reload();
// });