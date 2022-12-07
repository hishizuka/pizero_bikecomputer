import asyncio
from aiohttp import web
#from aiohttp.web_runner import GracefulExit

class server():

  config = None
  status = False
  message_keys = ["app", "title", "message"]

  def __init__(self, config):
    self.config = config
    self.http_server = web.Application()
    self.http_server.add_routes([web.get('/message', self.message_handler)])
    #self.http_server.add_routes([web.get('/shutdown', self.shutdown_handler)])

    self.runner = web.AppRunner(self.http_server)
    #don't exist loop
    #self.config.loop.run_until_complete(self.runner.setup())
    #self.site = web.TCPSite(self.runner)
  
  async def on_off_server(self):
    if not self.status: 
      await self.start()
    else:
      await self.stop()

  async def start(self):
    if not self.status:
      await self.runner.setup()
      self.site = web.TCPSite(self.runner)
      await self.site.start()
      self.status = True
  
  async def stop(self):
    if self.status:
      await self.site.stop()
      self.status = False

  def format_message(self, text_dic):
    if text_dic['title'] is None:
      return ''
    if text_dic['message'] is None:
      return ''

    formatted = '{title}: {message}'.format(**text_dic)
    return formatted

  async def message_handler(self, request):
    params = request.rel_url.query
    message = {}
    
    for key in self.message_keys:
      if key in params:
        message[key] = params[key]
      else:
        message[key] = ''
    formatted = self.format_message(message)
    if formatted is not None:
      print(formatted)
      await self.config.gui.show_message(message['title'], message['message'])
    
    #return web.Response()
    return web.Response(text="OK")

  #async def shutdown_handler(self, request):
  #  print("will shutdown now")
  #  raise GracefulExit()
