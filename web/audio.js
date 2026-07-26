
function color_loop_file() {
	document.querySelectorAll('.replay-button .playImage circle').forEach(e => {
        e.classList.remove("color_loop_file", "color_loop_AudioList");
    });
    document.querySelectorAll('.replay-button .playImage path').forEach(e => {
        e.classList.add("color_loop_file");
    });
}

function color_loop_AudioList() {
	document.querySelectorAll('.replay-button .playImage path').forEach(e => {
        e.classList.remove("color_loop_file", "color_loop_AudioList");
    });
    document.querySelectorAll('.replay-button .playImage circle').forEach(e => {
		e.classList.add("color_loop_AudioList");
    });
}

function color_loop_file_AND_AudioList() {
    document.querySelectorAll('.replay-button .playImage path').forEach(e => {
		e.classList.add("color_loop_file");
    });
	document.querySelectorAll('.replay-button .playImage circle').forEach(e => {
		e.classList.add("color_loop_AudioList");
    });
}

function color_loop_reset() {
    document.querySelectorAll('.replay-button .playImage path, .replay-button .playImage circle').forEach(e => {
        e.classList.remove("color_loop_file", "color_loop_AudioList");
    });
}

function playAudioFiles() {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.play();
    });
}

function setAudioPlaybackRate1(value) {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.playbackRate = value;
    });
}

function setAudioPlaybackRate2(value) {
    Array.from(document.getElementsByTagName("audio")).forEach(e => {
        e.playbackRate = value;
    });
}

function addAudioPlaybackRate(step) {
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


window.updateProgress = function(filename, timeStr, percentStr) {
    //console.log('updateProgress', filename, timeStr, percentStr);
    document.querySelectorAll(`.replay-button[data-fileortts="${filename}"] .progress-text`).forEach(text => {
        //console.log('Found progress-text', text);
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