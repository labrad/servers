// send keys to websocket and echo the response
$(document).ready(function() {
    // create websocket
    if (! ("WebSocket" in window)) WebSocket = MozWebSocket; // firefox
    var socket = new WebSocket("ws://localhost:8076");

    // open the socket
    socket.onopen = function(event) {
	socket.send('connected');

	// show server response
	socket.onmessage = function(e) {
	    $("#output").text(e.data);
	}

	// for each typed key send #entry's text to server
	$("#entry").keyup(function (e) {
	    socket.send($("#entry").attr("value"));
	});

    $("#data_req").click(function (e){
        socket.send('Give me data');
    });
    }
});