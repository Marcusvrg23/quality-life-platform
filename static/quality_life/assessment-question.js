// Progressive enhancement for the question page. The server enforces every rule.
(function () {
  "use strict";

  // Character counter for open answers: "12/150 caracteres", announced politely.
  document.querySelectorAll("[data-counter]").forEach(function (field) {
    var counter = document.getElementById(field.dataset.counter);
    if (!counter) return;
    counter.setAttribute("aria-live", "polite");
    var update = function () {
      counter.textContent = field.value.length + "/" + field.maxLength + " caracteres";
    };
    field.addEventListener("input", update);
    update();
  });

  // Exclusive option ("Não sinto dores") clears the others, and vice versa.
  var boxes = Array.prototype.slice.call(document.querySelectorAll('input[name="options"]'));
  boxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (!box.checked) return;
      boxes.forEach(function (other) {
        if (other !== box && (box.hasAttribute("data-exclusive") || other.hasAttribute("data-exclusive"))) {
          other.checked = false;
        }
      });
    });
  });
})();
