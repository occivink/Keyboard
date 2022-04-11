# Keyboard

TODO: find a name

Semi-modular, split, "ergonomic" keyboard design, designed for handwiring. Only CAD files for 3D-printing as of yet, firmware (intended for raspberry pico as of yet) will come later (maybe, if I actually go through with this).

Configurability is achieved by keeping the code simple and decently organized, so that one can change the design as they see fit.
Things that could be customized in theory:
* number of rows
* number of columns
* column stagger
* switch type (regular/kailh choc)
* keys in the thumb cluster
* shape and position of the thumb cluster (defined using a bezier curve)
* 'curved' aspect
The customizability is not infinite so some things would have to be changed other than just a constant, but the code tries to limit such assumptions.

TODO: illustrate this with screenshots
