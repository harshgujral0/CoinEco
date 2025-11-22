document.addEventListener('DOMContentLoaded', function(){
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const captureBtn = document.getElementById('captureBtn');
  const retakeBtn = document.getElementById('retakeBtn');
  const photoData = document.getElementById('photo_data');

  // Start webcam
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ video: true })
      .then(stream => { video.srcObject = stream; })
      .catch(err => alert("❌ Camera not available: " + err));
  } else {
    alert("Your browser does not support webcam.");
  }

  // Capture photo
  captureBtn.addEventListener('click', function(){
    canvas.style.display = 'block';
    video.style.display = 'none';
    captureBtn.style.display = 'none';
    retakeBtn.style.display = 'inline-block';

    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataURL = canvas.toDataURL('image/jpeg');
    photoData.value = dataURL;
  });

  // Retake photo
  retakeBtn.addEventListener('click', function(){
    canvas.style.display = 'none';
    video.style.display = 'block';
    captureBtn.style.display = 'inline-block';
    retakeBtn.style.display = 'none';

    photoData.value = ""; // clear old photo
  });
});
