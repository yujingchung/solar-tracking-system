#!/usr/bin/env python3
# coordinate_mapping_combined_english.py
"""
Dual Coordinate System Mapping Visualization
Left: Tip-Tilt System (γ, ζ)
Right: Azimuth-Tilt System (φ, β)
Using color mapping to show correspondence
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import hsv_to_rgb

# Set Times New Roman font
plt.rcParams['font.family'] = 'Times New Roman'
plt.rcParams['axes.unicode_minus'] = False


def generate_combined_mapping(csv_file, output_file='mapping_combined.png'):
    """
    Generate combined mapping with dual-variable color encoding
    - Hue represents azimuth (φ)
    - Brightness represents tilt angle (β)
    - With example points annotated
    """
    # Load data
    df = pd.read_csv(csv_file)
    print(f"✓ Loaded data: {len(df)} records")

    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # Create composite color mapping
    # H: Hue (0-360°, corresponds to azimuth)
    # S: Saturation (fixed)
    # V: Value/Brightness (corresponds to tilt angle)

    hue = df['phi'] / 360.0  # Normalize to 0-1
    saturation = np.ones_like(hue) * 0.9  # High saturation
    value = df['beta'] / df['beta'].max()  # Normalize brightness

    # Convert HSV to RGB
    hsv = np.stack([hue, saturation, value], axis=1)
    rgb = hsv_to_rgb(hsv)

    # Left plot: Azimuth-Tilt System (SWAPPED)
    ax1.scatter(df['phi'], df['beta'],
                c=rgb, s=15, alpha=0.6, edgecolors='none')
    ax1.set_xlabel('Azimuth, φ  (°)', fontsize=13, fontweight='bold')
    ax1.set_ylabel('Tilt Angle, β  (°)', fontsize=13, fontweight='bold')
    ax1.set_title('Azimuth-Tilt System\nHue=Azimuth | Brightness=Tilt',
                  fontsize=14, fontweight='bold', pad=15)
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.set_xlim(-10, 370)
    ax1.set_ylim(-2, 50)

    # Right plot: Tip-Tilt System (SWAPPED)
    ax2.scatter(df['gamma'], df['zeta'],
                c=rgb, s=15, alpha=0.6, edgecolors='none')
    ax2.set_xlabel('N-S Tilt Angle, γ  (°)', fontsize=13, fontweight='bold')
    ax2.set_ylabel('E-W Tilt Angle, ζ  (°)', fontsize=13, fontweight='bold')
    ax2.set_title('Tip-Tilt System\nHue=Azimuth | Brightness=Tilt',
                  fontsize=14, fontweight='bold', pad=15)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.set_aspect('equal')
    ax2.axhline(y=0, color='k', linewidth=0.5, alpha=0.3)
    ax2.axvline(x=0, color='k', linewidth=0.5, alpha=0.3)

    # Annotate key points - 4 actual test configurations
    examples = [
        {'beta': 10, 'phi': 160, 'label': 'A', 'color': 'red'},
        {'beta': 10, 'phi': 180, 'label': 'B', 'color': 'blue'},
        {'beta': 20, 'phi': 180, 'label': 'C', 'color': 'green'},
        {'beta': 30, 'phi': 200, 'label': 'D', 'color': 'orange'},
    ]

    for ex in examples:
        # Find corresponding data point using nearest neighbor search
        # Calculate distance in (beta, phi) space
        distances = np.sqrt((df['beta'] - ex['beta']) ** 2 + (df['phi'] - ex['phi']) ** 2)
        nearest_idx = distances.idxmin()
        row = df.loc[nearest_idx]

        # Only use if distance is reasonable (within 2 degrees)
        if distances[nearest_idx] < 2.0:
            # Left plot annotation (Azimuth-Tilt)
            ax1.plot(row['phi'], row['beta'], 'o',
                     color=ex['color'], markersize=12,
                     markeredgewidth=2, markeredgecolor='white')
            ax1.text(row['phi'], row['beta'] + 2, ex['label'],
                     ha='center', fontsize=12, fontweight='bold',
                     color=ex['color'])

            # Right plot annotation (Tip-Tilt)
            ax2.plot(row['gamma'], row['zeta'], 'o',
                     color=ex['color'], markersize=12,
                     markeredgewidth=2, markeredgecolor='white')
            ax2.text(row['gamma'], row['zeta'] + 2, ex['label'],
                     ha='center', fontsize=12, fontweight='bold',
                     color=ex['color'])

    # Add legend
    legend_text = (
        'A: β=10° φ=160°\n'
        'B: β=10° φ=180°\n'
        'C: β=20° φ=180°\n'
        'D: β=30° φ=200°'
    )
    ax1.text(0.02, 0.98, legend_text,
             transform=ax1.transAxes,
             fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    plt.suptitle('Dual-Variable Color Mapping (with Examples)\n(Hue = φ Azimuth | Brightness = β Tilt)',
                 fontsize=16, fontweight='bold', y=0.98)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Generated: {output_file}")
    plt.close()


def main():
    """Main function"""
    import sys

    print("\n" + "=" * 70)
    print("Dual Coordinate System Mapping Visualization")
    print("=" * 70)

    # Check CSV file
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = input("\nEnter CSV file path [default: tiptilt_conversion_step1.csv]: ").strip()
        if not csv_file:
            csv_file = 'tiptilt_conversion_step1.csv'

    # Generate combined mapping
    try:
        generate_combined_mapping(csv_file)
        print("\n" + "=" * 70)
        print("✓ Visualization complete!")
        print("=" * 70)
    except FileNotFoundError:
        print(f"❌ File not found: {csv_file}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()