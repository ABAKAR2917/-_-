function splitValues(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function syncTags(hidden) {
  const target = document.querySelector(`[data-tags-for="${hidden.id}"]`);
  if (!target) return;
  target.innerHTML = "";
  splitValues(hidden.value).forEach((skill) => {
    const tag = document.createElement("button");
    tag.type = "button";
    tag.className = "tag";
    tag.textContent = skill;
    tag.title = "Удалить";
    tag.addEventListener("click", () => {
      hidden.value = splitValues(hidden.value)
        .filter((item) => item.toLowerCase() !== skill.toLowerCase())
        .join(", ");
      syncTags(hidden);
    });
    target.appendChild(tag);
  });
}

function addValue(hidden, value) {
  const clean = value.trim();
  if (!clean) return;
  const values = splitValues(hidden.value);
  const exists = values.some((item) => item.toLowerCase() === clean.toLowerCase());
  if (!exists) {
    values.push(clean);
    hidden.value = values.join(", ");
    syncTags(hidden);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const backButton = document.querySelector("[data-back-button]");
  if (backButton) {
    backButton.addEventListener("click", () => {
      let canUseHistory = false;
      try {
        canUseHistory = document.referrer && new URL(document.referrer).origin === window.location.origin;
      } catch {
        canUseHistory = false;
      }
      if (canUseHistory && window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = "/";
      }
    });
  }

  const roleSelect = document.querySelector('select[name="role"]');
  const employerCodeRow = document.querySelector("[data-employer-code-row]");
  if (roleSelect && employerCodeRow) {
    const checkbox = employerCodeRow.querySelector('input[type="checkbox"]');
    const syncEmployerCodeRow = () => {
      const isEmployer = roleSelect.value === "employer";
      employerCodeRow.hidden = !isEmployer;
      if (!isEmployer && checkbox) checkbox.checked = false;
    };
    syncEmployerCodeRow();
    roleSelect.addEventListener("change", syncEmployerCodeRow);
  }

  document.querySelectorAll("[data-multi-picker]").forEach((input) => {
    const hidden = document.getElementById(input.dataset.target);
    if (!hidden) return;
    syncTags(hidden);

    input.addEventListener("change", () => {
      addValue(hidden, input.value);
      input.value = "";
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addValue(hidden, input.value);
        input.value = "";
      }
    });

    input.form?.addEventListener("submit", () => {
      addValue(hidden, input.value);
      input.value = "";
    });
  });
});
