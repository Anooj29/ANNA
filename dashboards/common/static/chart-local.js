/**
 * ANNA Self-Contained Offline Charting Engine (Chart.js compatibility fallback)
 * Renders Doughnut, Bar, and Line charts onto HTML5 Canvas without external CDN dependencies.
 */
(function() {
  if (typeof window.Chart !== 'undefined') return;

  class OfflineChart {
    constructor(ctx, config) {
      this.canvas = ctx.canvas || ctx;
      this.ctx = this.canvas.getContext('2d');
      this.config = config || {};
      this.type = this.config.type || 'line';
      this.data = this.config.data || { labels: [], datasets: [] };
      this.options = this.config.options || {};
      this.render();
    }

    destroy() {
      if (this.ctx && this.canvas) {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      }
    }

    update() {
      this.render();
    }

    render() {
      const c = this.canvas;
      const ctx = this.ctx;
      if (!c || !ctx) return;

      const rect = c.getBoundingClientRect();
      const width = rect.width || c.width || 400;
      const height = rect.height || c.height || 220;
      c.width = width;
      c.height = height;

      ctx.clearRect(0, 0, width, height);

      if (this.type === 'doughnut' || this.type === 'pie') {
        this.renderDoughnut(width, height);
      } else if (this.type === 'bar') {
        this.renderBar(width, height);
      } else {
        this.renderLine(width, height);
      }
    }

    renderDoughnut(w, h) {
      const ctx = this.ctx;
      const ds = this.data.datasets && this.data.datasets[0];
      if (!ds || !ds.data || ds.data.length === 0) return;

      const data = ds.data;
      const bg = Array.isArray(ds.backgroundColor) ? ds.backgroundColor : ['#2563eb', '#10b981', '#f59e0b', '#ef4444'];
      const total = data.reduce((a, b) => a + Number(b || 0), 0) || 1;

      const cx = w / 2;
      const cy = h / 2 - 12;
      const radius = Math.min(cx, cy) * 0.78;
      const innerRadius = this.type === 'doughnut' ? radius * 0.65 : 0;

      let startAngle = -Math.PI / 2;
      for (let i = 0; i < data.length; i++) {
        const sliceAngle = (Number(data[i] || 0) / total) * 2 * Math.PI;
        const endAngle = startAngle + sliceAngle;

        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, endAngle);
        ctx.arc(cx, cy, innerRadius, endAngle, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = bg[i % bg.length];
        ctx.fill();

        startAngle = endAngle;
      }

      if (this.data.labels && this.data.labels.length) {
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        let lx = cx - (this.data.labels.length * 45);
        this.data.labels.forEach((lbl, idx) => {
          ctx.fillStyle = bg[idx % bg.length];
          ctx.fillRect(lx, h - 18, 10, 10);
          ctx.fillStyle = '#475569';
          ctx.fillText(lbl, lx + 28, h - 10);
          lx += 90;
        });
      }
    }

    renderBar(w, h) {
      const ctx = this.ctx;
      const labels = this.data.labels || [];
      const datasets = this.data.datasets || [];
      if (labels.length === 0 || datasets.length === 0) return;

      const padLeft = 40;
      const padBottom = 35;
      const padTop = 20;
      const padRight = 20;
      const chartW = w - padLeft - padRight;
      const chartH = h - padTop - padBottom;

      let maxVal = 1;
      datasets.forEach(ds => {
        (ds.data || []).forEach(v => {
          if (Number(v) > maxVal) maxVal = Number(v);
        });
      });
      maxVal = Math.ceil(maxVal * 1.15);

      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padLeft, padTop);
      ctx.lineTo(padLeft, padTop + chartH);
      ctx.lineTo(padLeft + chartW, padTop + chartH);
      ctx.stroke();

      const groupW = chartW / labels.length;
      const numDs = datasets.length;
      const barW = Math.max(8, (groupW * 0.6) / numDs);

      labels.forEach((lbl, gi) => {
        const gCenter = padLeft + gi * groupW + groupW / 2;
        datasets.forEach((ds, di) => {
          const val = Number(ds.data[gi] || 0);
          const barH = (val / maxVal) * chartH;
          const bx = gCenter - ((numDs * barW) / 2) + (di * barW);
          const by = padTop + chartH - barH;

          ctx.fillStyle = Array.isArray(ds.backgroundColor) ? ds.backgroundColor[gi % ds.backgroundColor.length] : (ds.backgroundColor || '#2563eb');
          ctx.fillRect(bx, by, barW - 2, barH);
        });

        ctx.fillStyle = '#64748b';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(lbl, gCenter, padTop + chartH + 18);
      });
    }

    renderLine(w, h) {
      const ctx = this.ctx;
      const labels = this.data.labels || [];
      const datasets = this.data.datasets || [];
      if (labels.length === 0 || datasets.length === 0) return;

      const padLeft = 45;
      const padBottom = 35;
      const padTop = 20;
      const padRight = 25;
      const chartW = w - padLeft - padRight;
      const chartH = h - padTop - padBottom;

      let minVal = Infinity;
      let maxVal = -Infinity;
      datasets.forEach(ds => {
        (ds.data || []).forEach(v => {
          const n = Number(v);
          if (!isNaN(n)) {
            if (n < minVal) minVal = n;
            if (n > maxVal) maxVal = n;
          }
        });
      });
      if (minVal === Infinity) { minVal = 0; maxVal = 100; }
      if (minVal === maxVal) { minVal -= 5; maxVal += 5; }
      const range = (maxVal - minVal) || 1;

      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padLeft, padTop);
      ctx.lineTo(padLeft, padTop + chartH);
      ctx.lineTo(padLeft + chartW, padTop + chartH);
      ctx.stroke();

      const stepX = labels.length > 1 ? chartW / (labels.length - 1) : chartW;

      datasets.forEach((ds) => {
        const color = ds.borderColor || ds.backgroundColor || '#2563eb';
        const data = ds.data || [];
        ctx.strokeStyle = color;
        ctx.lineWidth = ds.borderWidth || 2;
        ctx.beginPath();

        data.forEach((val, idx) => {
          const x = padLeft + idx * stepX;
          const y = padTop + chartH - ((Number(val) - minVal) / range) * chartH;
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();

        ctx.fillStyle = color;
        data.forEach((val, idx) => {
          const x = padLeft + idx * stepX;
          const y = padTop + chartH - ((Number(val) - minVal) / range) * chartH;
          ctx.beginPath();
          ctx.arc(x, y, 3.5, 0, Math.PI * 2);
          ctx.fill();
        });
      });

      ctx.fillStyle = '#64748b';
      ctx.font = '11px sans-serif';
      ctx.textAlign = 'center';
      labels.forEach((lbl, idx) => {
        const x = padLeft + idx * stepX;
        ctx.fillText(lbl, x, padTop + chartH + 18);
      });
    }
  }

  window.Chart = OfflineChart;
})();
