import numpy as np

from numba import njit, objmode

import mcdc.kernel as kernel

from mcdc.constant import *
from mcdc.print_   import print_progress, print_progress_eigenvalue

# =========================================================================
# Simulation loop
# =========================================================================

@njit
def loop_simulation(mcdc):
    simulation_end = False
    while not simulation_end:
        # Loop over source particles
        loop_source(mcdc)
        
        # Eigenvalue cycle closeout
        if mcdc['setting']['mode_eigenvalue']:
            # Tally history closeout
            kernel.global_tally_closeout_history(mcdc)
            if mcdc['cycle_active']:
                kernel.tally_closeout_history(mcdc)
            
            # Print progress
            with objmode():
                print_progress_eigenvalue(mcdc)

            # Manage particle banks
            kernel.manage_particle_banks(mcdc)

            # Cycle management
            mcdc['i_cycle'] += 1
            if mcdc['i_cycle'] == mcdc['setting']['N_cycle']: 
                simulation_end = True
            elif mcdc['i_cycle'] >= mcdc['setting']['N_inactive']:
                mcdc['cycle_active'] = True

        # Fixed-source closeout
        else:
            simulation_end = True

    # Tally closeout
    kernel.tally_closeout(mcdc)    


# =========================================================================
# Source loop
# =========================================================================

@njit
def loop_source(mcdc):
    # Rebase rng skip_ahead seed
    kernel.rng_skip_ahead_strides(mcdc['mpi_work_start'], mcdc)
    kernel.rng_rebase(mcdc)

    # Progress bar indicator
    N_prog = 0
    
    # Loop over particle sources
    for work_idx in range(mcdc['mpi_work_size']):
        # Initialize RNG wrt work index
        kernel.rng_skip_ahead_strides(work_idx, mcdc)

        # Get a source particle and put into active bank
        if mcdc['bank_source']['size'] == 0:
            # Sample source
            xi  = kernel.rng(mcdc)
            tot = 0.0
            for S in mcdc['sources']:
                tot += S['prob']
                if tot >= xi:
                    break
            P = kernel.source_particle(S, mcdc)
            kernel.set_universe(P, mcdc)
        else:
            P = mcdc['bank_source']['particles'][work_idx]
        kernel.add_particle(P, mcdc['bank_active'])

        # Run the source particle and its secondaries
        # (until active bank is exhausted)
        while mcdc['bank_active']['size'] > 0:
            # Get particle from active bank
            P = kernel.pop_particle(mcdc['bank_active'])

            # Apply weight window
            if mcdc['technique']['weight_window']:
                kernel.weight_window(P, mcdc)
            
            # Particle loop
            loop_particle(P, mcdc)

        # Tally history closeout
        if not mcdc['setting']['mode_eigenvalue']:
            kernel.tally_closeout_history(mcdc)
        
        # Progress printout
        percent = (work_idx+1.0)/mcdc['mpi_work_size']
        if mcdc['setting']['progress_bar'] and int(percent*100.0) > N_prog:
            N_prog += 1
            with objmode(): 
                print_progress(percent, mcdc)

        
# =========================================================================
# Particle loop
# =========================================================================

@njit
def loop_particle(P, mcdc):
    while P['alive']:
        # Determine and move to event
        kernel.move_to_event(P, mcdc)
        event = P['event']

        # Collision
        if event == EVENT_COLLISION:
            # Generate IC?
            if mcdc['technique']['IC_generator'] and mcdc['cycle_active']:
                kernel.bank_IC(P, mcdc)

            # Branchless collision?
            if mcdc['technique']['branchless_collision']:
                kernel.branchless_collision(P, mcdc)

            # Normal collision
            else:
                # Get collision type
                event = kernel.collision(P, mcdc)

                # Perform collision
                if event == EVENT_CAPTURE:
                    kernel.capture(P, mcdc)
                elif event == EVENT_SCATTERING:
                    kernel.scattering(P, mcdc)
                elif event == EVENT_FISSION:
                    kernel.fission(P, mcdc)

        # Mesh crossing
        elif event == EVENT_MESH:
            kernel.mesh_crossing(P, mcdc)

        # Surface crossing
        elif event == EVENT_SURFACE:
            kernel.surface_crossing(P, mcdc)

        # Lattice crossing
        elif event == EVENT_LATTICE:
            kernel.lattice_crossing(P, mcdc)
    
        # Surface and mesh crossing
        elif event == EVENT_SURFACE_N_MESH:
            kernel.mesh_crossing(P, mcdc)
            kernel.surface_crossing(P, mcdc)

        # Lattice and mesh crossing
        elif event == EVENT_LATTICE_N_MESH:
            kernel.mesh_crossing(P, mcdc)
            kernel.lattice_crossing(P, mcdc)

        # Time boundary
        elif event == EVENT_TIME_BOUNDARY:
            kernel.time_boundary(P, mcdc)

        # Apply weight window
        if mcdc['technique']['weight_window']:
            kernel.weight_window(P, mcdc)
