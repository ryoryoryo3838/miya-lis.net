const canvas = document.getElementById("boids-canvas");
const ctx = canvas.getContext("2d");
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

const NUM_BOIDS = 50;
const BOID_SIZE = 6;
let mouse = { x: null, y: null };

canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect();
  mouse.x = e.clientX - rect.left;
  mouse.y = e.clientY - rect.top;
});
class Boid {
  constructor() {
    this.position = {
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height
    };
    const angle = Math.random() * 2 * Math.PI;
    this.velocity = {
      x: Math.cos(angle),
      y: Math.sin(angle)
    };
  }

  update(boids) {
    const perceptionRadius = 60;
    let align = { x: 0, y: 0 };
    let cohesion = { x: 0, y: 0 };
    let separation = { x: 0, y: 0 };
    let total = 0;

    for (const other of boids) {
      const dx = other.position.x - this.position.x;
      const dy = other.position.y - this.position.y;
      const d = Math.sqrt(dx * dx + dy * dy);

      if (other !== this && d < perceptionRadius) {
        // alignment
        align.x += other.velocity.x;
        align.y += other.velocity.y;
        // cohesion
        cohesion.x += other.position.x;
        cohesion.y += other.position.y;
        // separation
        separation.x += (this.position.x - other.position.x) / d;
        separation.y += (this.position.y - other.position.y) / d;
        total++;
      }
    }

    if (total > 0) {
      // alignment
      align.x /= total;
      align.y /= total;
      // cohesion
      cohesion.x /= total;
      cohesion.y /= total;
      cohesion.x -= this.position.x;
      cohesion.y -= this.position.y;
      // separation already normalized

      // weight
      align.x *= 0.05;
      align.y *= 0.05;
      cohesion.x *= 0.005;
      cohesion.y *= 0.005;
      separation.x *= 0.05;
      separation.y *= 0.05;

      this.velocity.x += align.x + cohesion.x + separation.x;
      this.velocity.y += align.y + cohesion.y + separation.y;
    }

    // limit speed
    const speed = Math.sqrt(this.velocity.x ** 2 + this.velocity.y ** 2);
    const maxSpeed = 2;
    if (speed > maxSpeed) {
      this.velocity.x = (this.velocity.x / speed) * maxSpeed;
      this.velocity.y = (this.velocity.y / speed) * maxSpeed;
    }

    this.position.x += this.velocity.x;
    this.position.y += this.velocity.y;

    // wrap around screen
    if (this.position.x < 0) this.position.x = canvas.width;
    if (this.position.x > canvas.width) this.position.x = 0;
    if (this.position.y < 0) this.position.y = canvas.height;
    if (this.position.y > canvas.height) this.position.y = 0;

    // マウスからの回避行動（force = repulsion）
    if (mouse.x !== null && mouse.y !== null) {
      const dx = this.position.x - mouse.x;
      const dy = this.position.y - mouse.y;
      const distSq = dx * dx + dy * dy;

      const avoidanceRadius = 80; // ピクセル
      if (distSq < avoidanceRadius * avoidanceRadius) {
        const dist = Math.sqrt(distSq);
        const strength = 100 / (distSq + 1); // 力は距離の逆数
        this.velocity.x += (dx / dist) * strength;
        this.velocity.y += (dy / dist) * strength;
      }
    }
  }
  draw(ctx) {
    const angle = Math.atan2(this.velocity.y, this.velocity.x);
    ctx.save();
    ctx.translate(this.position.x, this.position.y);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.moveTo(BOID_SIZE, 0);
    ctx.lineTo(-BOID_SIZE, BOID_SIZE / 2);
    ctx.lineTo(-BOID_SIZE, -BOID_SIZE / 2);
    ctx.closePath();
    ctx.fillStyle = "#00ffe1";
    ctx.fill();
    ctx.restore();
  }


}

const boids = Array.from({ length: NUM_BOIDS }, () => new Boid());

function animate() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const boid of boids) {
    boid.update(boids);
    boid.draw(ctx);
  }
  requestAnimationFrame(animate);
}

animate();

window.addEventListener("resize", () => {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
});

