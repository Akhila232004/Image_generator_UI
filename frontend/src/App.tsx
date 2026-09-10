import "./App.css";

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">✦</div>

          <div>
            <h1>Image Generator</h1>
            <p>Reference-driven creative workspace</p>
          </div>
        </div>

        <div className="header-actions">
          <button className="header-button">Documentation</button>
          <button className="icon-button" aria-label="Settings">
            ⚙
          </button>
        </div>
      </header>

      <main className="app-main">
        <section className="hero-section">
          <div>
            <span className="eyebrow">OBJECTIVES IMAGE GENERATOR</span>

            <h2>
              Transform references into
              <span> reusable visual content.</span>
            </h2>

            <p className="hero-description">
              Build a template from your reference and prompt, then use that
              template to generate new content.
            </p>
          </div>
        </section>

        <section className="workflow-section">
          <div className="workflow-step active">
            <div className="step-number">01</div>
            <div>
              <strong>Reference</strong>
              <span>Add source material</span>
            </div>
          </div>

          <div className="workflow-line" />

          <div className="workflow-step">
            <div className="step-number">02</div>
            <div>
              <strong>Template</strong>
              <span>Build reusable structure</span>
            </div>
          </div>

          <div className="workflow-line" />

          <div className="workflow-step">
            <div className="step-number">03</div>
            <div>
              <strong>Image Builder</strong>
              <span>Generate new content</span>
            </div>
          </div>

          <div className="workflow-line" />

          <div className="workflow-step">
            <div className="step-number">04</div>
            <div>
              <strong>Output</strong>
              <span>View generated files</span>
            </div>
          </div>
        </section>

        <section className="workspace">
          <div className="workspace-card">
            <div className="section-header">
              <div>
                <span className="section-number">01</span>
                <div>
                  <h3>Reference</h3>
                  <p>
                    Add an image, GIF, PDF, video or online reference.
                  </p>
                </div>
              </div>
            </div>

            <div className="placeholder-content">
              <div className="placeholder-icon">＋</div>
              <h4>Add your reference</h4>
              <p>
                Your selected reference preview will appear here.
              </p>
            </div>
          </div>

          <div className="workspace-card">
            <div className="section-header">
              <div>
                <span className="section-number">02</span>
                <div>
                  <h3>Template</h3>
                  <p>
                    Reference + prompt become your reusable template.
                  </p>
                </div>
              </div>
            </div>

            <div className="placeholder-content template-placeholder">
              <div className="template-icon">◇</div>
              <h4>Template workspace</h4>
              <p>
                Generate and refine the template from your reference.
              </p>
            </div>
          </div>
        </section>

        <section className="builder-card">
          <div className="section-header">
            <div>
              <span className="section-number">03</span>
              <div>
                <h3>Image Builder</h3>
                <p>
                  Use the generated template and content prompt to create
                  your output.
                </p>
              </div>
            </div>

            <span className="coming-soon-badge">
              Canva + MCP · Coming later
            </span>
          </div>

          <div className="builder-placeholder">
            <div className="builder-icon">✦</div>
            <div>
              <h4>Ready to generate</h4>
              <p>
                Template, content prompt and AI configuration will be
                connected here.
              </p>
            </div>
          </div>
        </section>

        <section className="output-card">
          <div className="section-header">
            <div>
              <span className="section-number">04</span>
              <div>
                <h3>Output</h3>
                <p>
                  Generated files are stored in the project output folder.
                </p>
              </div>
            </div>

            <span className="output-path">output/</span>
          </div>

          <div className="output-empty">
            <div className="output-icon">□</div>
            <h4>No generated outputs yet</h4>
            <p>
              Your generated images, PDFs, GIFs and videos will appear here.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;