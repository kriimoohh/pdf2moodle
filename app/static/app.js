/* Page d'upload : sélection du fichier, envoi avec progression, aperçu. */

(function () {
  "use strict";

  var form = document.getElementById("form");
  var drop = document.getElementById("drop");
  var input = document.getElementById("file");
  var dropFile = document.getElementById("drop-file");
  var submit = document.getElementById("submit");
  var progress = document.getElementById("progress");
  var fill = document.getElementById("progress-fill");
  var progressText = document.getElementById("progress-text");
  var alertBox = document.getElementById("alert");
  var result = document.getElementById("result");
  var resultMeta = document.getElementById("result-meta");
  var download = document.getElementById("download");
  var preview = document.getElementById("preview");
  var restart = document.getElementById("restart");

  var objectUrl = null;

  function showError(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
  }
  function clearError() {
    alertBox.hidden = true;
    alertBox.textContent = "";
  }
  function humanSize(bytes) {
    return bytes < 1024 * 1024
      ? Math.max(1, Math.round(bytes / 1024)) + " Ko"
      : (bytes / 1024 / 1024).toFixed(1) + " Mo";
  }

  /* ------------------------------------------------------- choix du fichier */

  function selectFile(file) {
    clearError();
    if (!file) { return; }
    if (!/\.pdf$/i.test(file.name)) {
      showError("Merci de sélectionner un fichier PDF.");
      return;
    }
    var transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;

    dropFile.textContent = file.name + " — " + humanSize(file.size);
    dropFile.hidden = false;
    drop.classList.add("has-file");
    submit.disabled = false;
  }

  drop.addEventListener("click", function () { input.click(); });
  drop.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", function () { selectFile(input.files[0]); });

  ["dragenter", "dragover"].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.remove("dragover");
    });
  });
  drop.addEventListener("drop", function (event) {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      selectFile(event.dataTransfer.files[0]);
    }
  });
  /* Empêche le navigateur d'ouvrir un PDF déposé à côté de la zone. */
  ["dragover", "drop"].forEach(function (name) {
    window.addEventListener(name, function (event) {
      if (!drop.contains(event.target)) { event.preventDefault(); }
    });
  });

  /* -------------------------------------------------------------- réponses */

  function filenameFromHeader(header) {
    var match = header && header.match(/filename="([^"]+)"/);
    return match ? match[1] : "support.html";
  }

  /* Les erreurs arrivent en JSON alors que la réponse est lue en Blob :
     il faut relire le corps en texte pour récupérer le message du serveur. */
  function reportFailure(xhr) {
    var fallback = "La conversion a échoué (code " + xhr.status + ").";
    var blob = xhr.response;
    if (!(blob instanceof Blob)) {
      showError(fallback);
      return;
    }
    blob.text().then(function (text) {
      try {
        var payload = JSON.parse(text);
        showError(payload.error || payload.detail || fallback);
      } catch (err) {
        showError(xhr.status === 401 ? "Authentification requise." : fallback);
      }
    }).catch(function () { showError(fallback); });
  }

  function showResult(xhr) {
    var blob = xhr.response;
    var name = filenameFromHeader(xhr.getResponseHeader("Content-Disposition"));
    var pageCount = xhr.getResponseHeader("X-Page-Count");

    if (objectUrl) { URL.revokeObjectURL(objectUrl); }
    objectUrl = URL.createObjectURL(blob);

    download.href = objectUrl;
    download.setAttribute("download", name);
    preview.src = objectUrl;

    resultMeta.textContent =
      (pageCount ? pageCount + " pages · " : "") + name + " · " + humanSize(blob.size);

    result.hidden = false;
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ---------------------------------------------------------------- envoi */

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!input.files.length) { return; }

    clearError();
    result.hidden = true;
    submit.disabled = true;
    progress.hidden = false;
    fill.style.width = "0%";
    progressText.textContent = "Envoi en cours…";

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/convert");
    xhr.responseType = "blob";
    xhr.withCredentials = true;

    xhr.upload.addEventListener("progress", function (event) {
      if (!event.lengthComputable) { return; }
      var percent = Math.round((event.loaded / event.total) * 100);
      fill.style.width = percent + "%";
      if (percent >= 100) {
        progressText.textContent = "Conversion en cours, patientez…";
      }
    });

    xhr.addEventListener("load", function () {
      progress.hidden = true;
      submit.disabled = false;
      if (xhr.status >= 200 && xhr.status < 300) {
        showResult(xhr);
      } else {
        reportFailure(xhr);
      }
    });
    xhr.addEventListener("error", function () {
      progress.hidden = true;
      submit.disabled = false;
      showError("Connexion au serveur impossible.");
    });

    xhr.send(new FormData(form));
  });

  restart.addEventListener("click", function () {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    preview.removeAttribute("src");
    result.hidden = true;
    form.reset();
    input.value = "";
    dropFile.hidden = true;
    drop.classList.remove("has-file");
    submit.disabled = true;
    clearError();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();
