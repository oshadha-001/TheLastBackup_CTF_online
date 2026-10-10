import html
def archive_page(title,body):
    return '<h1>'+html.escape(title)+'</h1>'+body
