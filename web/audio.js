
window.color_loop_file = function() {
    //console.log('color_loop_file');
	document.querySelectorAll('.replay-button').forEach(e => {
        e.classList.remove("color_loop_file", "color_loop_AudioList");
    });
    document.querySelectorAll('.replay-button').forEach(e => {
        e.classList.add("color_loop_file");
    });
}

window.color_loop_AudioList = function() {
    //console.log('color_loop_AudioList');
	document.querySelectorAll('.replay-button').forEach(e => {
        e.classList.remove("color_loop_file", "color_loop_AudioList");
    });
    document.querySelectorAll('.replay-button').forEach(e => {
		e.classList.add("color_loop_AudioList");
    });
}

window.color_loop_file_AND_AudioList = function() {
    document.querySelectorAll('.replay-button').forEach(e => {
		e.classList.add("color_loop_file");
    });
	document.querySelectorAll('.replay-button').forEach(e => {
		e.classList.add("color_loop_AudioList");
    });
}

window.color_loop_reset = function() {
    document.querySelectorAll('.replay-button').forEach(e => {
        e.classList.remove("color_loop_file", "color_loop_AudioList");
    });
}

window.playAudioFiles = function() {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.play();
    });
}

window.setAudioPlaybackRate1 = function(value) {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.playbackRate = value;
    });
}

window.setAudioPlaybackRate2 = function (value) {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.playbackRate = value;
    });
}

window.addAudioPlaybackRate = function (step) {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.playbackRate += step;
    });
}




window.setActiveButtons = function(filename) {
	//console.log('setActiveButtons:', filename);
    document.querySelectorAll('.replay-button.playing').forEach(el => el.classList.remove('playing'));
    document.querySelectorAll(`.replay-button[data-fileortts="${filename}"]`).forEach(el => el.classList.add('playing'));
};

window.clearActive = function() {
	//console.log('clearActive');
    document.querySelectorAll('.replay-button.playing').forEach(el => el.classList.remove('playing'));
    document.querySelectorAll('.progress-text').forEach(el => el.remove());
};


window.createTextPrg = function(filename) {
	//console.log('createTextPrg', filename);
	window.setActiveButtons(filename);
	let fel = 0;
	document.querySelectorAll(`.replay-button[data-fileortts="${filename}"] .playImage`).forEach(svg => {
		//console.log('Found svg', svg);
		let text = svg.querySelector('.progress-text');
		if (!text) {
			text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
			text.setAttribute('x', '32');
			text.setAttribute('y', '28');
			text.setAttribute('text-anchor', 'middle');
			text.setAttribute('font-size', '14');
			text.setAttribute('fill', 'coral');
			text.setAttribute('class', 'progress-text');
			svg.appendChild(text);
		}
		text.innerHTML = '';
		fel += 1;
	});
	return fel;
}


window.ensureProgressText = function(filename) {
    //console.log('ensureProgressText called for', filename);
	let fel = createTextPrg(filename);
	if(fel == 0) {
		setTimeout(() => {
			createTextPrg(filename);
		}, 500);
	}
};


window.updateProgress = function(filename, timeStr, percentStr, is_paused) {
    //console.log('updateProgress', filename, timeStr, percentStr);
    let attpause = "false";
    if(is_paused) attpause = "true";        

    document.querySelectorAll(`.replay-button[data-fileortts="${filename}"] .progress-text`).forEach(text => {
        //console.log('Found progress-text', text);
        if( !(text.getAttribute("is_paused") === attpause) ) {
            text.setAttribute("is_paused", attpause);
            if(attpause === "true") text.setAttribute("fill", "red");
            else text.setAttribute("fill", "coral");        
        }            
        
        text.innerHTML = '';
        var tspan1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tspan1.setAttribute('x', '32');
        tspan1.setAttribute('dy', '5px');
        tspan1.textContent = timeStr;
        text.appendChild(tspan1);
        
        var tspan2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tspan2.setAttribute('x', '32');
        tspan2.setAttribute('dy', '15px');
        tspan2.textContent = percentStr;
        text.appendChild(tspan2);
    });
};