import logging
from flexget.feed import Entry
from flexget.plugin import register_plugin, PluginError, get_plugin_by_name

log = logging.getLogger('emit_imdb')


class EmitIMDBQueue(object):
    """
    Use your imdb queue as an input by emitting the content of it
    """

    def validator(self):
        from flexget import validator
        return validator.factory('boolean')

    def on_feed_input(self, feed):
        if not feed.config.get("emit_imdb_queue"):
            return

        imdb_entries = get_plugin_by_name('imdb_queue_manager').\
               instance.queue_get()

        for imdb_entry in imdb_entries:
            entry = Entry()
            # make sure the entry has IMDB fields filled
            entry['url'] = ''
            entry['imaginary'] = True
            entry['imdb_url'] = 'http://www.imdb.com/title/' + imdb_entry.imdb_id
            entry['imdb_id'] = imdb_entry.imdb_id
            
            # check if title is a imdb url (leftovers from old database?)
            # TODO: maybe this should be fixed at the queue_get ...
            if 'http://' in imdb_entry.title:
                log.debug('queue contains url instead of title')
                try:
                    get_plugin_by_name('imdb_lookup').instance.\
                        lookup(feed, entry)
                except PluginError:
                    log.error("Found imdb url in imdb queue, "\
                              "but lookup failed: %s" % entry['imdb_url'])
                    continue
                entry['title'] = entry['imdb_name']
            else:
                # normal title
                entry['title'] = imdb_entry.title

            feed.entries.append(entry)
            log.debug("Added title and IMDB id to new entry: %s - %s" %
                     (entry['title'], entry['imdb_id']))

register_plugin(EmitIMDBQueue, 'emit_imdb_queue')
