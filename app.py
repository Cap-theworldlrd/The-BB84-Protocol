import streamlit as pd_streamlit_app
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
    .stApp {
        background-color: #080E1E;
        color: #F0F4F8;
    }

    section[data-testid="stSidebar"] {
        background-color: #0D162D !important;
        border-right: 1px solid #1E2D5A;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #00E5FF !important;
    }

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

    h1, h2, h3 {
        color: #00E5FF !important;
        font-family: 'Trebuchet MS', sans-serif;
    }

    p {
        color: #C0C8D8;
    }

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
        self.bases = np.random.choice(
            ['Z', 'X'],
            size=size
        )  # Z = Rectilinear, X = Diagonal

    def encode(self):
        """
        BB84 polarization encoding:

        Z basis:
            bit 0 -> 0°
            bit 1 -> 90°

        X basis:
            bit 0 -> 45°
            bit 1 -> 135°
        """
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
        """
        Educational intercept-resend attack.

        Eve independently decides whether to intercept each photon.
        If intercepted, she randomly chooses a basis, measures the photon,
        and resends the corresponding collapsed polarization state.
        """
        intercepted_states = []
        self.bases = []
        self.results = []

        for state in states:

            if np.random.random() < self.prob_intercept:
                basis = np.random.choice(['Z', 'X'])
                self.bases.append(basis)

                # Eve measures in the Z basis
                if basis == 'Z':
                    prob_0 = (np.cos(np.radians(state))) ** 2

                    result = (
                        0
                        if np.random.random() < prob_0
                        else 1
                    )

                    collapsed_state = (
                        0.0 if result == 0 else 90.0
                    )

                # Eve measures in the X basis
                else:
                    prob_plus = (
                        np.cos(np.radians(state - 45.0))
                    ) ** 2

                    result = (
                        0
                        if np.random.random() < prob_plus
                        else 1
                    )

                    collapsed_state = (
                        45.0 if result == 0 else 135.0
                    )

                self.results.append(result)
                intercepted_states.append(collapsed_state)

            else:
                # Photon passes through without Eve interaction.
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
        """
        Bob measures each received photon.

        The channel_noise parameter is an educational abstraction:
        when triggered, Bob's measurement result is replaced by a random bit.
        This is not a physical model of polarization noise.
        """
        self.results = []

        for state, basis in zip(states, self.bases):

            # Simplified environmental/channel noise model
            if np.random.random() < channel_noise:
                self.results.append(np.random.randint(2))
                continue

            # Ideal Z-basis measurement
            if basis == 'Z':
                prob_0 = (
                    np.cos(np.radians(state))
                ) ** 2

                result = (
                    0
                    if np.random.random() < prob_0
                    else 1
                )

            # Ideal X-basis measurement
            else:
                prob_plus = (
                    np.cos(np.radians(state - 45.0))
                ) ** 2

                result = (
                    0
                    if np.random.random() < prob_plus
                    else 1
                )

            self.results.append(result)

        return np.array(self.results)


class BB84Simulation:
    def __init__(
        self,
        num_qubits,
        eve_prob=0.0,
        noise=0.0,
        sacrifice_pct=0.20,
        threshold=0.11
    ):
        self.num_qubits = num_qubits
        self.eve_prob = eve_prob
        self.noise = noise
        self.sacrifice_pct = sacrifice_pct
        self.threshold = threshold

        self.alice = Alice(num_qubits)
        self.eve = Eve(eve_prob)
        self.bob = Bob(num_qubits)

    def run(self):

        # ---------------------------------------------------------------------
        # 1. Alice prepares and transmits photons
        # ---------------------------------------------------------------------
        sent_states = self.alice.encode()

        # ---------------------------------------------------------------------
        # 2. Eve attempts intercept-resend attack
        # ---------------------------------------------------------------------
        channel_states = self.eve.attack(sent_states)

        # ---------------------------------------------------------------------
        # 3. Bob measures received photons
        # ---------------------------------------------------------------------
        bob_results = self.bob.measure(
            channel_states,
            self.noise
        )

        # ---------------------------------------------------------------------
        # 4. Basis reconciliation / sifting
        # ---------------------------------------------------------------------
        sifted_indices = [
            i
            for i in range(self.num_qubits)
            if self.alice.bases[i] == self.bob.bases[i]
        ]

        sifted_len = len(sifted_indices)

        if sifted_len == 0:
            return {
                "aborted": True,
                "reason": "No bases matched during reconciliation.",
                "qber": 0.0,
                "sifted_len": 0,
                "sacrifice_len": 0,
                "final_len": 0,
                "alice_key": "",
                "bob_key": "",
                "alice_hash": "N/A",
                "bob_hash": "N/A",
                "keys_match": False,
                "sifted_indices": [],
                "sacrifice_indices": [],
                "remaining_indices": []
            }

        # ---------------------------------------------------------------------
        # 5. Public QBER estimation
        # ---------------------------------------------------------------------
        num_sacrifice = max(
            1,
            int(sifted_len * self.sacrifice_pct)
        )

        sacrifice_indices = np.random.choice(
            sifted_indices,
            size=num_sacrifice,
            replace=False
        )

        errors = sum(
            1
            for i in sacrifice_indices
            if self.alice.bits[i] != self.bob.results[i]
        )

        estimated_qber = errors / num_sacrifice

        # ---------------------------------------------------------------------
        # 6. Determine whether protocol should abort
        # ---------------------------------------------------------------------
        is_secure = estimated_qber < self.threshold

        # ---------------------------------------------------------------------
        # 7. Remove publicly tested bits
        # ---------------------------------------------------------------------
        remaining_indices = [
            i
            for i in sifted_indices
            if i not in sacrifice_indices
        ]

        alice_key_bits = [
            self.alice.bits[i]
            for i in remaining_indices
        ]

        bob_key_bits = [
            self.bob.results[i]
            for i in remaining_indices
        ]

        candidate_alice_key = "".join(
            map(str, alice_key_bits)
        )

        candidate_bob_key = "".join(
            map(str, bob_key_bits)
        )

        # ---------------------------------------------------------------------
        # 8. Educational consistency check
        #
        # IMPORTANT:
        # SHA-256 here is NOT a replacement for authenticated classical
        # communication, information reconciliation, or privacy amplification.
        # It is only used to demonstrate that the two simulated strings match.
        # ---------------------------------------------------------------------
        if is_secure:
            alice_hash = (
                hashlib.sha256(
                    candidate_alice_key.encode()
                ).hexdigest()[:16]
                if candidate_alice_key
                else "N/A"
            )

            bob_hash = (
                hashlib.sha256(
                    candidate_bob_key.encode()
                ).hexdigest()[:16]
                if candidate_bob_key
                else "N/A"
            )

            alice_key_str = candidate_alice_key
            bob_key_str = candidate_bob_key
            keys_match = alice_key_str == bob_key_str

        else:
            # Candidate key material is explicitly discarded on abort.
            alice_key_str = ""
            bob_key_str = ""
            alice_hash = "DISCARDED"
            bob_hash = "DISCARDED"
            keys_match = False

        return {
            "aborted": not is_secure,
            "qber": estimated_qber,
            "sifted_len": sifted_len,
            "sacrifice_len": num_sacrifice,
            "final_len": len(remaining_indices) if is_secure else 0,
            "alice_key": alice_key_str,
            "bob_key": bob_key_str,
            "alice_hash": alice_hash,
            "bob_hash": bob_hash,
            "keys_match": keys_match,
            "sifted_indices": sifted_indices,
            "sacrifice_indices": list(sacrifice_indices),
            "remaining_indices": remaining_indices if is_secure else []
        }


# -----------------------------------------------------------------------------
# APPLICATION HEADER
# -----------------------------------------------------------------------------
pd_streamlit_app.title(
    "⚛️ BB84 Protocol: Interactive Quantum Cryptography Simulator"
)

pd_streamlit_app.markdown(
    "An educational software testbench that simulates the core stages of the "
    "BB84 quantum key distribution protocol, including polarization encoding, "
    "basis reconciliation, QBER estimation, channel noise, and an "
    "intercept-resend eavesdropping attack."
)

pd_streamlit_app.info(
    "ℹ️ **Educational model:** This simulator demonstrates the core BB84 "
    "concepts but does not implement a complete production QKD system. "
    "Information reconciliation, authenticated classical communication, "
    "and privacy amplification are not fully implemented."
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
    help="Initial number of polarized single photons transmitted by Alice."
)

eve_active = pd_streamlit_app.sidebar.checkbox(
    "Enable Eavesdropper (Eve)",
    value=True,
    help="Enable an educational intercept-resend attack on the quantum channel."
)

if eve_active:
    eve_prob = pd_streamlit_app.sidebar.slider(
        "Eve Interception Probability",
        min_value=0.1,
        max_value=1.0,
        value=1.0,
        step=0.1,
        help="Approximate probability that Eve intercepts an individual photon."
    )
else:
    eve_prob = 0.0

noise_rate = pd_streamlit_app.sidebar.slider(
    "Channel Environmental Noise",
    min_value=0.00,
    max_value=0.20,
    value=0.02,
    step=0.01,
    help=(
        "Simplified educational noise model that randomly replaces Bob's "
        "measurement outcome."
    )
)

abort_threshold = pd_streamlit_app.sidebar.slider(
    "Security Abort Threshold (QBER)",
    min_value=0.05,
    max_value=0.25,
    value=0.11,
    step=0.01,
    help=(
        "Demonstration threshold. A run is aborted when the estimated QBER "
        "is equal to or greater than this value."
    )
)

sacrifice_ratio = pd_streamlit_app.sidebar.slider(
    "Sacrifice Ratio (QBER Test Sample)",
    min_value=0.10,
    max_value=0.40,
    value=0.20,
    step=0.05,
    help=(
        "Fraction of sifted bits publicly compared to estimate the QBER."
    )
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
# DASHBOARD METRICS
# -----------------------------------------------------------------------------
col1, col2, col3, col4 = pd_streamlit_app.columns(4)

with col1:
    pd_streamlit_app.metric(
        label="Sifted Bits",
        value=f"{results['sifted_len']} bits",
        delta=f"~{results['sifted_len'] / total_qubits:.1%}"
    )

with col2:
    qber_color = (
        "normal"
        if results["qber"] < abort_threshold
        else "inverse"
    )

    pd_streamlit_app.metric(
        label="Estimated QBER",
        value=f"{results['qber']:.2%}",
        delta=f"Abort threshold: {abort_threshold:.0%}",
        delta_color=qber_color
    )

with col3:
    status_str = (
        "ACCEPTED ✅"
        if not results["aborted"]
        else "ABORTED ❌"
    )

    pd_streamlit_app.metric(
        label="Protocol Status",
        value=status_str
    )

with col4:
    if results["aborted"]:
        match_str = "DISCARDED ⚠️"
    else:
        match_str = (
            "MATCH ✅"
            if results.get("keys_match", False)
            else "MISMATCH ❌"
        )

    pd_streamlit_app.metric(
        label="Candidate Key Check",
        value=match_str
    )


# -----------------------------------------------------------------------------
# SECURITY STATUS ALERT
# -----------------------------------------------------------------------------
if results["aborted"]:

    pd_streamlit_app.error(
        f"🚨 **Protocol Aborted:** The estimated QBER of "
        f"**{results['qber']:.2%}** is equal to or greater than the selected "
        f"demonstration threshold of **{abort_threshold:.2%}**. "
        f"Candidate key material has been discarded."
    )

else:

    pd_streamlit_app.success(
        f"🎉 **Protocol Accepted:** The estimated QBER of "
        f"**{results['qber']:.2%}** is below the selected demonstration "
        f"threshold of **{abort_threshold:.2%}**. "
        f"**{results['final_len']} candidate key bits** remain after the "
        f"QBER test sample was removed."
    )


# -----------------------------------------------------------------------------
# DETAILED SIMULATION VISUALIZATIONS
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = pd_streamlit_app.tabs(
    [
        "📊 Analytical Plots",
        "🔍 Qubit-by-Qubit Technical Ledger",
        "🔬 Key Reconciliation Summary"
    ]
)


# -----------------------------------------------------------------------------
# TAB 1 — ANALYTICAL PLOTS
# -----------------------------------------------------------------------------
with tab1:

    pd_streamlit_app.subheader(
        "Channel Statistics & Performance Analysis"
    )

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(15, 5)
    )

    fig.patch.set_facecolor('#080E1E')

    # -------------------------------------------------------------------------
    # Chart 1: Sifting Breakdown
    # -------------------------------------------------------------------------
    labels = [
        'QBER Test Bits',
        'Remaining Candidate Key',
        'Basis-Mismatched'
    ]

    discarded_len = (
        total_qubits - results['sifted_len']
    )

    sizes = [
        results['sacrifice_len'],
        results['final_len'],
        discarded_len
    ]

    colors = [
        '#FFC107',
        '#00E5FF',
        '#1E2D5A'
    ]

    ax1.set_facecolor('#080E1E')

    # Only draw a pie chart if there is something to display.
    if sum(sizes) > 0:

        wedges, texts, autotexts = ax1.pie(
            sizes,
            labels=labels,
            autopct='%1.1f%%',
            startangle=140,
            colors=colors,
            textprops=dict(color="w")
        )

        for autotext in autotexts:
            autotext.set_color('black')
            autotext.set_weight('bold')

    ax1.set_title(
        "Photon Transmission Composition",
        color='#00E5FF',
        fontsize=14,
        pad=15
    )

    # -------------------------------------------------------------------------
    # Chart 2: QBER Comparison
    # -------------------------------------------------------------------------
    ax2.set_facecolor('#121B31')

    bars = ax2.bar(
        ['Estimated QBER', 'Abort Threshold'],
        [
            results['qber'] * 100,
            abort_threshold * 100
        ],
        color=[
            '#FF4B4B'
            if results['qber'] >= abort_threshold
            else '#00E5FF',
            '#1E2D5A'
        ],
        width=0.4
    )

    ax2.set_ylabel(
        'Error Rate (%)',
        color='w'
    )

    ax2.set_title(
        'Quantum Bit Error Rate vs Abort Boundary',
        color='#00E5FF',
        fontsize=14,
        pad=15
    )

    ax2.tick_params(colors='w')

    ax2.spines['bottom'].set_color('#1E2D5A')
    ax2.spines['top'].set_color('none')
    ax2.spines['left'].set_color('#1E2D5A')
    ax2.spines['right'].set_color('none')

    # Annotate bars with percentage values
    for bar in bars:

        height = bar.get_height()

        ax2.annotate(
            f'{height:.2f}%',
            xy=(
                bar.get_x() + bar.get_width() / 2,
                height
            ),
            xytext=(0, 3),
            textcoords="offset points",
            ha='center',
            va='bottom',
            color='w',
            weight='bold'
        )

    pd_streamlit_app.pyplot(
        fig,
        use_container_width=True
    )

    plt.close(fig)


# -----------------------------------------------------------------------------
# TAB 2 — TECHNICAL LEDGER
# -----------------------------------------------------------------------------
with tab2:

    pd_streamlit_app.subheader(
        "Qubit-by-Qubit Mathematical Log"
    )

    pd_streamlit_app.markdown(
        "Inspect the simulated physical and mathematical states of each "
        "transmitted photon. When Alice and Bob choose different bases, "
        "the measurement result is not used for the sifted key. Eve's "
        "intercept-resend measurements can introduce errors when her basis "
        "choice differs from Alice's."
    )

    polarization_symbols = {
        0.0: "↑ (0°)",
        90.0: "→ (90°)",
        45.0: "↗ (45°)",
        135.0: "↖ (135°)"
    }

    records = []

    for i in range(total_qubits):

        # ---------------------------------------------------------------------
        # Correct Alice polarization-state calculation
        # ---------------------------------------------------------------------
        if sim.alice.bases[i] == 'Z':

            state = (
                0.0
                if sim.alice.bits[i] == 0
                else 90.0
            )

        else:

            state = (
                45.0
                if sim.alice.bits[i] == 0
                else 135.0
            )

        alice_state_desc = polarization_symbols.get(
            state,
            f"{state}°"
        )

        eve_b = (
            sim.eve.bases[i]
            if eve_active
            else "-"
        )

        eve_r = (
            sim.eve.results[i]
            if (
                eve_active
                and sim.eve.results[i] != -1
            )
            else "-"
        )

        match_status = (
            "YES"
            if sim.alice.bases[i] == sim.bob.bases[i]
            else "NO"
        )

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

    def style_dataframe(row):

        if row["Bases Match?"] == "YES":

            return [
                "background-color: #12253B; color: #00E5FF"
            ] * len(row)

        return [
            "background-color: #0A0F1D; color: #5B6B8A"
        ] * len(row)

    styled_df = df.style.apply(
        style_dataframe,
        axis=1
    )

    pd_streamlit_app.dataframe(
        styled_df,
        use_container_width=True,
        height=450
    )


# -----------------------------------------------------------------------------
# TAB 3 — KEY RECONCILIATION
# -----------------------------------------------------------------------------
with tab3:

    pd_streamlit_app.subheader(
        "Key Sifting and Educational Consistency Check"
    )

    if results["aborted"]:

        pd_streamlit_app.warning(
            "🔑 **Key Synthesis Blocked:** "
            "The protocol was aborted because the estimated QBER reached "
            "or exceeded the selected threshold. Candidate key material "
            "has been discarded."
        )

        pd_streamlit_app.markdown(
            "No candidate key or hash is displayed because the protocol "
            "did not pass the simulated QBER security test."
        )

    else:

        st_col1, st_col2 = pd_streamlit_app.columns(2)

        with st_col1:

            pd_streamlit_app.markdown(
                "### 👩‍💻 Alice's Candidate Key"
            )

            pd_streamlit_app.text_area(
                "Alice's Remaining Key Bits",
                value=results["alice_key"],
                height=80,
                disabled=True,
                key="alice_sifted_key_text"
            )

            pd_streamlit_app.code(
                f"Educational SHA-256 Check: "
                f"{results['alice_hash']}",
                language="text"
            )

        with st_col2:

            pd_streamlit_app.markdown(
                "### 👨‍💻 Bob's Candidate Key"
            )

            pd_streamlit_app.text_area(
                "Bob's Remaining Key Bits",
                value=results["bob_key"],
                height=80,
                disabled=True,
                key="bob_sifted_key_text"
            )

            pd_streamlit_app.code(
                f"Educational SHA-256 Check: "
                f"{results['bob_hash']}",
                language="text"
            )

        pd_streamlit_app.markdown("---")

        pd_streamlit_app.markdown(
            "### 📦 Key Finalization Status"
        )

        if results["keys_match"]:

            pd_streamlit_app.success(
                "The two simulated candidate key strings are identical."
            )

        else:

            pd_streamlit_app.error(
                "The two simulated candidate key strings do not match."
            )

        pd_streamlit_app.markdown(
            "The SHA-256 values shown above are used only as an "
            "**educational consistency check** to demonstrate that identical "
            "key strings produce identical hash values. This does not provide "
            "authenticated classical communication and should not be treated "
            "as a replacement for QKD authentication."
        )

        pd_streamlit_app.markdown(
            "A complete practical QKD system would additionally require "
            "**information reconciliation/error correction**, "
            "**privacy amplification**, and **authenticated classical "
            "communication**. These mechanisms are not fully implemented "
            "in this simulator."
        )

        pd_streamlit_app.info(
            "🔬 **Scope of this simulator:** "
            "This project demonstrates the core BB84 concepts of random basis "
            "selection, polarization encoding, quantum measurement, "
            "intercept-resend eavesdropping, basis sifting, QBER estimation, "
            "and candidate-key generation."
        )
