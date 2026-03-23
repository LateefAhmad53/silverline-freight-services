const reveals = document.querySelectorAll(".reveal");

const revealOnScreen = () => {
    const trigger = window.innerHeight * 0.9;
    reveals.forEach((item) => {
        const top = item.getBoundingClientRect().top;
        if (top < trigger) {
            item.classList.add("visible");
        }
    });
};

window.addEventListener("scroll", revealOnScreen);
window.addEventListener("load", revealOnScreen);

const progressSliders = document.querySelectorAll(".progress-slider");

progressSliders.forEach((slider) => {
    const targetId = slider.dataset.target;
    const output = targetId ? document.getElementById(targetId) : null;

    const renderValue = () => {
        if (output) {
            output.textContent = `${slider.value}%`;
        }
    };

    slider.addEventListener("input", renderValue);
    renderValue();
});
