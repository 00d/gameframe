import raycasterShader from './raycaster.wgsl?raw';

// ============================================================
// Renderer — WebGPU pipeline setup and frame dispatch
// ============================================================

export interface RendererConfig {
  canvas: HTMLCanvasElement;
  resolution: [number, number]; // [width, height]
}

export class DungeonRenderer {
  private device!: GPUDevice;
  private context!: GPUCanvasContext;

  private computePipeline!: GPUComputePipeline;
  private renderPipeline!: GPURenderPipeline;

  private cameraBuffer!: GPUBuffer;
  private mapParamsBuffer!: GPUBuffer;
  private mapDataBuffer!: GPUBuffer;
  private outputTexture!: GPUTexture;
  private bindGroup!: GPUBindGroup;
  private renderBindGroup!: GPUBindGroup;

  private resolution: [number, number];
  private initPromise: Promise<void>;

  // Blit shader — full-screen quad that displays the compute output
  private static readonly blitVS = `
    struct VSOut {
      @location(0) uv: vec2<f32>,
      @builtin(position) pos: vec4<f32>,
    };
    @vertex fn main(@builtin(vertex_index) i: u32) -> VSOut {
      let uv = vec2<f32>(f32(i & 1u), f32((i >> 1u) & 1u));
      return VSOut(uv, vec4<f32>(uv * 2.0 - 1.0, 0.0, 1.0));
    }
  `;

  private static readonly blitFS = `
    @group(0) @binding(0) var tex: texture_2d<f32>;
    @group(0) @binding(1) var sam: sampler;
    @fragment fn main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
      return textureSample(tex, sam, uv);
    }
  `;

  constructor(config: RendererConfig) {
    this.resolution = config.resolution;
    this.initPromise = this.init(config.canvas);
  }

  private async init(canvas: HTMLCanvasElement) {
    if (!navigator.gpu) {
      throw new Error('WebGPU is not supported in this browser. Please use Chrome, Edge, or another WebGPU-compatible browser.');
    }

    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) {
      throw new Error('No WebGPU adapter found. Your GPU may not support WebGPU.');
    }
    this.device = await adapter.requestDevice();

    this.context = canvas.getContext('webgpu')!;
    const format = navigator.gpu.getPreferredCanvasFormat();
    this.context.configure({ device: this.device, format });

    canvas.width = this.resolution[0];
    canvas.height = this.resolution[1];

    this.buildComputePipeline();
    this.buildRenderPipeline(format);
    this.createBuffers();
  }

  private buildComputePipeline() {
    const shaderModule = this.device.createShaderModule({ code: raycasterShader });
    this.computePipeline = this.device.createComputePipeline({
      layout: 'auto',
      compute: { module: shaderModule, entryPoint: 'main' },
    });
  }

  private buildRenderPipeline(format: GPUTextureFormat) {
    const vs = this.device.createShaderModule({ code: DungeonRenderer.blitVS });
    const fs = this.device.createShaderModule({ code: DungeonRenderer.blitFS });

    this.renderPipeline = this.device.createRenderPipeline({
      layout: 'auto',
      vertex: { module: vs, entryPoint: 'main' },
      fragment: {
        module: fs,
        entryPoint: 'main',
        targets: [{ format }],
      },
      primitive: { topology: 'triangle-strip' },
    });
  }

  private createBuffers() {
    const [w, h] = this.resolution;

    // Camera uniform: position(2) + angle(1) + fov(1) + resolution(2) + padding = 32 bytes
    this.cameraBuffer = this.device.createBuffer({
      size: 32,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    // Map params uniform: width(1) + height(1) = 8 bytes, padded to 16
    this.mapParamsBuffer = this.device.createBuffer({
      size: 16,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    // Map data: allocated on first loadMap() call
    // Output texture: compute writes RGBA, render reads it
    this.outputTexture = this.device.createTexture({
      size: [w, h],
      format: 'rgba8unorm',
      usage: GPUTextureUsage.STORAGE_BINDING | GPUTextureUsage.TEXTURE_BINDING,
    });
  }

  // --- Public API ---

  /**
   * Load a dungeon map. Grid values: 0 = open, >0 = wall type.
   */
  async loadMap(grid: Uint32Array, width: number, height: number) {
    await this.initPromise;
    // Create or recreate the map data buffer
    if (this.mapDataBuffer) this.mapDataBuffer.destroy();
    this.mapDataBuffer = this.device.createBuffer({
      size: grid.byteLength,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    });
    this.device.queue.writeBuffer(this.mapDataBuffer, 0, grid);

    // Write map dimensions
    this.device.queue.writeBuffer(
      this.mapParamsBuffer, 0,
      new Uint32Array([width, height])
    );

    this.rebuildBindGroups();
  }

  private rebuildBindGroups() {
    this.bindGroup = this.device.createBindGroup({
      layout: this.computePipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: { buffer: this.cameraBuffer } },
        { binding: 1, resource: { buffer: this.mapParamsBuffer } },
        { binding: 2, resource: { buffer: this.mapDataBuffer } },
        { binding: 3, resource: this.outputTexture.createView() },
      ],
    });

    this.renderBindGroup = this.device.createBindGroup({
      layout: this.renderPipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: this.outputTexture.createView() },
        { binding: 1, resource: this.device.createSampler({ minFilter: 'nearest', magFilter: 'nearest' }) },
      ],
    });
  }

  /**
   * Update camera state (called every frame before render).
   */
  setCamera(px: number, py: number, angle: number, fov: number) {
    const data = new Float32Array([
      px, py,           // position
      angle,            // angle
      fov,              // fov
      this.resolution[0], this.resolution[1], // resolution (as float for alignment)
      0, 0              // padding
    ]);
    this.device.queue.writeBuffer(this.cameraBuffer, 0, data);
  }

  /**
   * Dispatch compute + render. GPU commands are submitted asynchronously.
   * Note: This must only be called after initialization is complete (isReady = true).
   */
  frame() {
    if (!this.bindGroup) return; // map not loaded yet

    const encoder = this.device.createCommandEncoder();

    // --- Compute pass: raycaster ---
    const compute = encoder.beginComputePass();
    compute.setPipeline(this.computePipeline);
    compute.setBindGroup(0, this.bindGroup);
    // Dispatch one workgroup per 64 columns
    const dispatchX = Math.ceil(this.resolution[0] / 64);
    compute.dispatchWorkgroups(dispatchX);
    compute.end();

    // --- Render pass: blit to canvas ---
    const renderTarget = this.context.getCurrentTexture().createView();
    const render = encoder.beginRenderPass({
      colorAttachments: [{ view: renderTarget, clearValue: [0, 0, 0, 1], loadOp: 'clear', storeOp: 'store' }],
    });
    render.setPipeline(this.renderPipeline);
    render.setBindGroup(0, this.renderBindGroup);
    render.draw(4); // full-screen quad (triangle-strip)
    render.end();

    this.device.queue.submit([encoder.finish()]);
  }

  get isReady(): boolean {
    return !!this.bindGroup;
  }
}
