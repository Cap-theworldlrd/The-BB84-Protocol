import streamlit as pd_streamlit_app # Using standard alias wrapper to avoid any namespace collisions
import numpy as np
import matplotlib.pyplot as plt
import hashlib
import pandas as pd

# -----------------------------------------------------------------------------
# STREAMLIT PAGE CONFIGURATION
# -----------------------------------------------------------------------------
pd_streamlit_app.set_page_config(
    page_title="BB84 Quantum Key Distribution Simulator",
    page_icon="⚛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern cybersecurity dark-mode styling
pd_streamlit_app.markdown("""
    <style>
    /* Main body background and text */
    .stApp {
        background-color: #080E1E;
        color: #F0F4F8;
    }
    /* Side bar styling */
    section[data-testid="stSidebar"] {
        background-color: #0D162D !important;
        border-right: 1px solid #1E2D5A;
    }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
        color: #00E5FF !important;
    }
    /* Metric Card Custom Styling */
    div[data-testid="metric-container"] {
        background-color: #121B31;
        border: 1px solid #1E2D5A;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    div[data-testid="stMetricValue"] {
        color: #00E5FF !important;
        font-family: 'Trebuchet MS', sans-serif;
    }
    /* Header colors */
    h1, h2, h3 {
        color: #00E5FF !important;
        font-family: 'Trebuchet MS', sans-serif;
    }
    /* Subtitles */
    p {
        color: #C0C8D8;
    }
    /* Alert styling */
    .stAlert {
        background-color: #121B31 !important;
        border: 1px solid #1E2D5A !important;
        color: #F0F4F8 !important;
    }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# CORE SIMULATION ENGINE CLASSES
# -----------------------------------------------------------------------------
class Alice:
    def __init__(self, size):
        self.size = size
        self.bits = np.random.randint(2, size=size)
        self.bases = np.random.choice(['Z', 'X'], size=size)  # Z = Rectilinear (+), X = Diagonal (x)

    def encode(self):
        # Polarization state mapping in degrees:
        # Z-basis (Rect): 0 -> 0° (Vertical), 1 -> 90° (Horizontal)
        # X-basis (Diag): 0 -> 45° (Diag), 1 -> 135° (Anti-Diag)
        states = []
        for bit, basis in zip(self.bits, self.bases):
            if basis == 'Z':
                states.append(0.0 if bit == 0 else 90.0)
            else:
                states.append(45.0 if bit == 0 else 135.0)
        return np.array(states)

class Eve:
    def __init__(self, prob_intercept):
        self.prob_intercept = prob_intercept
        self.bases = []
        self.results = []

    def attack(self, states):
        intercepted_states = []
        self.bases = []
        self.results = []
        
        for state in states:
            # Determine if Eve intercepts this specific photon based on probability
            if np.random.random() < self.prob_intercept:
                basis = np.random.choice(['Z', 'X'])
                self.bases.append(basis)
                
                # Measure photon and collapse state
                if basis == 'Z':
                    # Measuring with vertical/horizontal filter
                    prob_0 = (np.cos(np.radians(state)))**2
                    result = 0 if np.random.random() < prob_0 else 1
                    collapsed_state = 0.0 if result == 0 else 90.0
                else:
                    # Measuring with diagonal filter
                    prob_plus = (np.cos(np.radians(state - 45.0)))**2
                    result = 0 if np.random.random() < prob_plus else 1
                    collapsed_state = 45.0 if result == 0 else 135.0
                    
                self.results.append(result)
                intercepted_states.append(collapsed_state)
            else:
                # Photon passes through untouched
                self.bases.append('-')
                self.results.append(-1)
                intercepted_states.append(state)
                
        return np.array(intercepted_states)

class Bob:
    def __init__(self, size):
        self.size = size
        self.bases = np.random.choice(['Z', 'X'], size=size)
        self.results = []

    def measure(self, states, channel_noise=0.0):
        self.results = []
        for state, basis in zip(states, self.bases):
            # Apply environmental thermal/mechanical noise
            if np.random.random() < channel_noise:
                # Noise completely randomizes Bob's outcome
                self.results.append(np.random.randint(2))
                continue
                
            # Perfect measurement mechanics
            if basis == 'Z':
                prob_0 = (np.cos(np.radians(state)))**2
                result = 0 if np.random.random() < prob_0 else 1
            else:
                prob_plus = (np.cos(np.radians(state - 45.0)))**2
                result = 0 if np.random.random() < prob_plus else 1
            self.results.append(result)
        return np.array(self.results)

class BB84Simulation:
    def __init__(self, num_qubits, eve_prob=0.0, noise=0.0, sacrifice_pct=0.20, threshold=0.11):
        self.num_qubits = num_qubits
        self.eve_prob = eve_prob
        self.noise = noise
        self.sacrifice_pct = sacrifice_pct
        self.threshold = threshold
        
        # Instantiate entities
        self.alice = Alice(num_qubits)
        self.eve = Eve(eve_prob)
        self.bob = Bob(num_qubits)
        
    def run(self):
        # 1. Alice prepares and transmits photons
        sent_states = self.alice.encode()
        
        # 2. Eve attempts interception
        channel_states = self.eve.attack(sent_states)
        
        # 3. Bob measures received states
        bob_results = self.bob.measure(channel_states, self.noise)
        
        # 4. Sifting / Basis Reconciliation
        sifted_indices = [i for i in range(self.num_qubits) if self.alice.bases[i] == self.bob.bases[i]]
        sifted_len = len(sifted_indices)
        
        if sifted_len == 0:
            return {
                "aborted": True, "reason": "No bases matched during reconciliation.",
                "qber": 0.0, "sifted_len": 0, "final_len": 0
            }
            
        # 5. Public Parameter Selection (Sacrifice subset to estimate QBER)
        num_sacrifice = max(1, int(sifted_len * self.sacrifice_pct))
        sacrifice_indices = np.random.choice(sifted_indices, size=num_sacrifice, replace=False)
        
        errors = sum(1 for i in sacrifice_indices if self.alice.bits[i] != self.bob.results[i])
        estimated_qber = errors / num_sacrifice
        
        # 6. Distill Secret Key
        remaining_indices = [i for i in sifted_indices if i not in sacrifice_indices]
        alice_key_bits = [self.alice.bits[i] for i in remaining_indices]
        bob_key_bits = [self.bob.results[i] for i in remaining_indices]
        
        alice_key_str = "".join(map(str, alice_key_bits))
        bob_key_str = "".join(map(str, bob_key_bits))
        
        # Generate SHA-256 integrity hashes
        alice_hash = hashlib.sha256(alice_key_str.encode()).hexdigest()[:16] if alice_key_str else "N/A"
        bob_hash = hashlib.sha256(bob_key_str.encode()).hexdigest()[:16] if bob_key_str else "N/A"
        
        is_secure = estimated_qber < self.threshold
        keys_match = alice_key_str == bob_key_str
        
        return {
            "aborted": not is_secure,
            "qber": estimated_qber,
            "sifted_len": sifted_len,
            "sacrifice_len": num_sacrifice,
            "final_len": len(remaining_indices),
            "alice_key": alice_key_str,
            "bob_key": bob_key_str,
            "alice_hash": alice_hash,
            "bob_hash": bob_hash,
            "keys_match": keys_match,
            "sifted_indices": sifted_indices,
            "sacrifice_indices": list(sacrifice_indices),
            "remaining_indices": remaining_indices
        }

# -----------------------------------------------------------------------------
# APPLICATION HEADER AND DASHBOARD LAYOUT
# -----------------------------------------------------------------------------
pd_streamlit_app.title("⚛️ BB84 Protocol: Interactive Quantum Cryptography Simulator")
pd_streamlit_app.markdown(
    "A software testbench developed to simulate physical-layer "
    "information-theoretically secure key distribution over an insecure optical channel. "
    "Adjust the parameters in the sidebar to simulate quantum behaviors, channel noise, and active eavesdropping attacks."
)

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
pd_streamlit_app.sidebar.header("⚙️ Simulation Settings")

total_qubits = pd_streamlit_app.sidebar.slider(
    "Total Transmitted Qubits (N)", 
    min_value=20, 
    max_value=200, 
    value=80, 
    step=10,
    help="The initial number of polarized single photons transmitted by Alice."
)

eve_active = pd_streamlit_app.sidebar.checkbox(
    "Enable Eavesdropper (Eve)", 
    value=True,
    help="Toggle whether Eve initiates an active Intercept-and-Resend attack on the quantum channel."
)

if eve_active:
    eve_prob = pd_streamlit_app.sidebar.slider(
        "Eve Interception Probability", 
        min_value=0.1, 
        max_value=1.0, 
        value=1.0, 
        step=0.1,
        help="The percentage of transmitted photons that Eve successfully intercepts and measures."
    )
else:
    eve_prob = 0.0

noise_rate = pd_streamlit_app.sidebar.slider(
    "Channel Environmental Noise (QBER Noise)", 
    min_value=0.00, 
    max_value=0.20, 
    value=0.02, 
    step=0.01,
    help="Simulates physical channel imperfections (thermal fluctuations or fiber misalignment) that randomize polarization."
)

abort_threshold = pd_streamlit_app.sidebar.slider(
    "Security Abort Threshold (QBER Max Limit)", 
    min_value=0.05, 
    max_value=0.25, 
    value=0.11, 
    step=0.01,
    help="The maximum tolerated QBER. If the estimated error rate exceeds this, Alice and Bob abort the key generation."
)

sacrifice_ratio = pd_streamlit_app.sidebar.slider(
    "Sacrifice Ratio (QBER Test Sample)", 
    min_value=0.10, 
    max_value=0.40, 
    value=0.20, 
    step=0.05,
    help="The proportion of matching sifted bits publicly compared to calculate channel integrity."
)

# -----------------------------------------------------------------------------
# SIMULATION EXECUTION
# -----------------------------------------------------------------------------
sim = BB84Simulation(
    num_qubits=total_qubits, 
    eve_prob=eve_prob, 
    noise=noise_rate, 
    sacrifice_pct=sacrifice_ratio, 
    threshold=abort_threshold
)
results = sim.run()

# -----------------------------------------------------------------------------
# DASHBOARD METRICS DISPLAY
# -----------------------------------------------------------------------------
col1, col2, col3, col4 = pd_streamlit_app.columns(4)

with col1:
    pd_streamlit_app.metric(
        label="Sifted Key Length", 
        value=f"{results['sifted_len']} bits", 
        delta=f"~{results['sifted_len']/total_qubits:.1%}"
    )

with col2:
    qber_color = "normal" if results["qber"] < abort_threshold else "inverse"
    pd_streamlit_app.metric(
        label="Estimated QBER", 
        value=f"{results['qber']:.2%}", 
        delta=f"Threshold: {abort_threshold:.0%}",
        delta_color=qber_color
    )

with col3:
    status_str = "SECURE ✅" if not results["aborted"] else "ABORTED ❌"
    pd_streamlit_app.metric(label="Channel Security Status", value=status_str)

with col4:
    match_str = "SUCCESS ✅" if results.get("keys_match", False) and not results["aborted"] else "N/A ⚠️" if results["aborted"] else "FAILED ❌"
    pd_streamlit_app.metric(label="Final Key Verification", value=match_str)

# Show alert depending on state
if results["aborted"]:
    pd_streamlit_app.error(
        f"🚨 **Quantum Channel Interrupted!** The estimated QBER of **{results['qber']:.2%}** is equal to or greater "
        f"than the specified security threshold of **{abort_threshold:.2%}**. Alice and Bob have discarded all sifted "
        f"bits to prevent a security compromise."
    )
else:
    pd_streamlit_app.success(
        f"🎉 **Secure Cryptographic Key Established!** The channel noise and intercept footprint converged to "
        f"**{results['qber']:.2%}**, remaining safely below the **{abort_threshold:.2%}** threshold. Alice and Bob "
        f"distilled a secure **{results['final_len']}-bit key**."
    )

# -----------------------------------------------------------------------------
# DETAILED SIMULATION VISUALIZATIONS
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = pd_streamlit_app.tabs(["📊 Interactive Analytical Plots", "🔍 Qubit-by-Qubit Technical Ledger", "🔬 Key Reconciliation Summary"])

with tab1:
    pd_streamlit_app.subheader("Channel Statistics & Performance Analysis")
    
    # Render interactive graphs
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))
    fig.patch.set_facecolor('#080E1E')
    
    # Chart 1: Key Sifting Breakdown
    labels = ['Sacrificed', 'Final Key', 'Discarded Bases']
    discarded_len = total_qubits - results['sifted_len']
    sizes = [results['sacrifice_len'], results['final_len'], discarded_len]
    colors = ['#FFC107', '#00E5FF', '#1E2D5A']
    
    ax1.set_facecolor('#080E1E')
    wedges, texts, autotexts = ax1.pie(
        sizes, labels=labels, autopct='%1.1f%%', 
        startangle=140, colors=colors, 
        textprops=dict(color="w")
    )
    for autotext in autotexts:
        autotext.set_color('black')
        autotext.set_weight('bold')
    ax1.set_title("Photon Transmission Composition", color='#00E5FF', fontsize=14, pad=15)
    
    # Chart 2: QBER Comparison Gauge
    ax2.set_facecolor('#121B31')
    bars = ax2.bar(
        ['Estimated QBER', 'Abort Threshold'], 
        [results['qber'], abort_threshold], 
        color=['#FF4B4B' if results['qber'] >= abort_threshold else '#00E5FF', '#1E2D5A'],
        width=0.4
    )
    ax2.set_ylabel('Error Rate (%)', color='w')
    ax2.set_title('Quantum Bit Error Rate vs Abort Boundary', color='#00E5FF', fontsize=14, pad=15)
    ax2.tick_params(colors='w')
    ax2.spines['bottom'].set_color('#1E2D5A')
    ax2.spines['top'].set_color('none')
    ax2.spines['left'].set_color('#1E2D5A')
    ax2.spines['right'].set_color('none')
    
    # Annotate bars
    for bar in bars:
        height = bar.get_height()
        ax2.annotate(f'{height:.2%}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom', color='w', weight='bold')
                    
    pd_streamlit_app.pyplot(fig)

with tab2:
    pd_streamlit_app.subheader("Qubit-by-Qubit Mathematical Log")
    pd_streamlit_app.markdown(
        "Inspect the physical and mathematical states of each transmitted single photon. Note how "
        "any discrepancy between Alice's and Bob's bases results in random results (marked in grey below), "
        "and how Eve's measurement collapses the states to introduce errors."
    )
    
    # Assemble a beautiful Pandas DataFrame mapping out the qubits
    polarization_symbols = {0.0: "↑ (0°)", 90.0: "→ (90°)", 45.0: "↗ (45°)", 135.0: "↖ (135°)"}
    
    records = []
    for i in range(total_qubits):
        state = 0.0 if sim.alice.bits[i] == 0 else 90.0 if sim.alice.bases[i] == 'Z' else 45.0 if sim.alice.bits[i] == 0 else 135.0
        alice_state_desc = polarization_symbols.get(state, f"{state}°")
        
        eve_b = sim.eve.bases[i] if eve_active else "-"
        eve_r = sim.eve.results[i] if (eve_active and sim.eve.results[i] != -1) else "-"
        
        match_status = "YES" if sim.alice.bases[i] == sim.bob.bases[i] else "NO"
        
        row = {
            "Qubit Index": i,
            "Alice's Bit": sim.alice.bits[i],
            "Alice's Basis": sim.alice.bases[i],
            "Alice's State": alice_state_desc,
            "Eve's Basis": eve_b,
            "Eve's Result": eve_r,
            "Bob's Basis": sim.bob.bases[i],
            "Bob's Measurement": sim.bob.results[i],
            "Bases Match?": match_status
        }
        records.append(row)
        
    df = pd.DataFrame(records)
    
    # Function to color match rows and grey out mismatches
    def style_dataframe(row):
        if row["Bases Match?"] == "YES":
            return ["background-color: #12253B; color: #00E5FF"] * len(row)
        return ["background-color: #0A0F1D; color: #5B6B8A"] * len(row)
        
    styled_df = df.style.apply(style_dataframe, axis=1)
    pd_streamlit_app.dataframe(styled_df, use_container_width=True, height=450)

with tab3:
    pd_streamlit_app.subheader("Key Sifting and Cryptographic Hashing")
    
    if results["aborted"]:
        pd_streamlit_app.warning("🔑 **Key Synthesis Blocked:** Key finalization was aborted due to security violations.")
    else:
        st_col1, st_col2 = pd_streamlit_app.columns(2)
        
        with st_col1:
            pd_streamlit_app.markdown("### 👩‍💻 Alice's Key Verification")
            pd_streamlit_app.text_area("Alice's Sifted Secret Key Bits", value=results["alice_key"], height=80, disabled=True, key="alice_sifted_key_text")
            pd_streamlit_app.code(f"Integrity Check Hash (SHA-256): {results['alice_hash']}", language="text")
            
        with st_col2:
            pd_streamlit_app.markdown("### 👨‍💻 Bob's Key Verification")
            pd_streamlit_app.text_area("Bob's Sifted Secret Key Bits", value=results["bob_key"], height=80, disabled=True, key="bob_sifted_key_text")
            pd_streamlit_app.code(f"Integrity Check Hash (SHA-256): {results['bob_hash']}", language="text")
            
        pd_streamlit_app.markdown("---")
        pd_streamlit_app.markdown("### 📦 Key Finalization Concept")
        pd_streamlit_app.markdown(
            "To complete the key exchange, Alice and Bob can now apply a **One-Way Cryptographic Hash** to verify their "
            "secret key matches perfectly, without ever transmitting the key itself over the public classical channel. "
            "In practical QKD networks, this step is followed by **Privacy Amplification** (extracting a shorter, highly "
            "secure key using hashing) and **Error Correction** (e.g. Cascade protocol) to fix minor environmental noise."
        )

