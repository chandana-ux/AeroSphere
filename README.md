# AeroSphere

> **From One Flight to a Trusted 3D World**

AeroSphere is a drone-based 3D reconstruction and spatial intelligence system that transforms aerial video and imagery into an interactive 3D environment.

---

## 🚀 Live Demo & Sample Datasets

### 🌐 Live Demo

**[Open AeroSphere Live Demo](https://aerosphere-sih2026.streamlit.app/)**

The live deployment provides the AeroSphere interface and interactive 3D visualization using the available demonstration reconstruction.

### 📦 Sample Datasets

Two sample drone videos are provided for testing the AeroSphere reconstruction workflow locally:

- 🎥 **[Sample Video 1](https://drive.google.com/file/d/1AjrKM-jf3pfT0a_jsvbuacKGPw9covfZ/view?usp=sharing)**
- 🎥 **[Sample Video 2](https://drive.google.com/file/d/17DQ5ATpLaA81MCZtIlJi5qhJi234GP11/view?usp=sharing)**

These samples can be used to demonstrate the workflow from frame selection through 3D reconstruction, mesh generation, and interactive 3D visualization.

These samples can be used to demonstrate the workflow from frame selection through 3D reconstruction and visualization.

> **Note:** The sample videos should be downloaded from the project-provided dataset location before running a reconstruction locally.

---

## 🎥 Recorded Video Demo

**[▶ Watch the AeroSphere Demo](https://youtu.be/LSXj__PzHMQ)**

The recorded demonstration shows the AeroSphere workflow from input footage and frame selection through 3D reconstruction, interactive visualization, and spatial intelligence.

---

## 🌐 What is AeroSphere?

AeroSphere converts drone footage into a navigable 3D representation of the captured environment.

Instead of treating drone footage as only a sequence of 2D frames, AeroSphere uses photogrammetric reconstruction to estimate camera positions, generate 3D points, create dense geometry, and produce an interactive 3D world.

The system combines:

- Drone video and image input
- Intelligent frame selection
- Camera pose estimation
- Sparse 3D reconstruction
- Dense reconstruction
- 3D mesh generation
- Point-cloud visualization
- Spatial intelligence
- Geo analysis
- Measurement capabilities

---

## 🎯 Problem

Drone footage contains valuable spatial information, but conventional video viewing provides only a sequence of 2D images.

For spatial analysis, users need to understand:

- Where cameras were positioned
- How the scene is structured in 3D
- How different areas relate spatially
- What geometry was reconstructed
- How measurements can be obtained from the reconstructed environment

AeroSphere brings these capabilities together in a single workflow.

---

## 💡 Our Solution

AeroSphere transforms drone footage into an interactive 3D environment through an automated reconstruction pipeline.

```text
Drone Video / Images
        ↓
Frame Selection
        ↓
Sparse Reconstruction
        ↓
Dense Reconstruction
        ↓
Mesh Generation
        ↓
Interactive 3D World
        ↓
Spatial Intelligence
        ↓
Geo / Measurement / Analysis