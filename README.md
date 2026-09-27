# bambi


## what

I've been talking about wanting a 3d printer for quite a while, where it was starting to become a part of my identity. To fix that, my wife surprised me one day with a gift of the p1s printer. I remember feeling this type of joy when my brothers and I got the n64 for christmas, pure boyish joy+excitement+chaos.

My previous ways for making 3d prints was the typical design process: build model (rhino) -> export to stl -> import and format for printer -> print

But that was back when I did everything manually and I had no technical experience with programming. Now, I want to explore what we can automate and build agentically.

So, here is what this fucking thing does right now.

- It provides some utility scripts for working with the bambu labs api so you can slice a model without having to open some yet another software and click yet another button. That's too many things to click on, in this economy?!
- To maximimize the vibing going on, we are utilizing the blender py package along with the mcp connection to build out the models. At some point when I miss the nurbs I'll bring in the rhino api. 
- It mimics a modeling session by creating a new folder with the project name and date. This folder contains all data the for whatever the fuck was created during that modeling session.


## how

This is all being built with macOS. To get started, you'll need to install blender and bambu-studio
```sh
brew install --cask blender bambu-studio
```

To add the agentic spice, I'm using the [blender-mcp](https://github.com/ahujasid/blender-mcp) add-on for live modeling with claude. If you run claude code or whatever shit you use it should be able to pull in the hacky skill for scaffolding up a new modelign session.

There is a `just` config here that is helpful for running recipes. 

```sh
brew install just

just                       # list all commands
just setup                 # uv sync, create .env, flatten Bambu Studio profiles into profiles/
just new phone-stand       # sessions/2026-09-26-phone-stand/ with an mm-unit model.blend, opened in Blender
just build phone-stand     # export STL, then run checks, then slice to out/*.gcode.3mf
just studio phone-stand    # open in Bambu Studio -> Print plate sends via Bambu Cloud
just status                # printer status (LAN)
just print phone-stand     # LAN: upload and start (asks first)
```

