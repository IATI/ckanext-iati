import uuid
import ckan.model as model
from sqlalchemy import Column
from sqlalchemy import types
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, DateTime, UnicodeText
from sqlalchemy import create_engine
from sqlalchemy import func
from ckan.plugins.toolkit import config
import logging

log = logging.getLogger(__name__)

Base = declarative_base()


def make_uuid():
    return unicode(uuid.uuid4())


class IATIRedirects(Base):
    """
    This table is to store old to new publisher id mapping and this can be utilized for redirects in the plugin
    """
    __tablename__ = 'iati_redirects'

    id = Column(UnicodeText, primary_key=True, default=make_uuid)
    group_id = Column(UnicodeText, nullable=False, index=True)
    old_name = Column(UnicodeText, nullable=False, index=True)
    current_name = Column(UnicodeText, nullable=True, index=True)
    updated = Column(DateTime(timezone=True), server_default=func.now(), index=False)

    @classmethod
    def update_redirects(cls):
        """
        Delete all the previous redirects and insert a new redirects
        :return: None
        """
        log.info("Updating redirects")
        model.Session.query(cls).delete()
        _data = cls._extract_redirects()
        for row in _data:
            redirect = cls()
            redirect.group_id = row[0]
            redirect.current_name = row[1]
            redirect.old_name = row[2]
            model.Session.add(redirect)

        try:
            # Commit and close the session
            model.Session.commit()
            model.Session.close()
        except Exception as e:
            # Rollback if any error
            model.Session.rollback()
            model.Session.close()
            log.error(e)
            raise ValueError("Something wrong while inserting values to db table")

    @staticmethod
    def _extract_redirects():
        """
        Extracts the required redirects from the database tables and return the result as tuple
        TODD: Change the below query using sqlalchemy
        This is data is used to store in the table iati_redirects
        :return: tuple
        """
        _db_conn = create_engine(config.get('sqlalchemy.url')).connect()
        _query = ''' 
                  SELECT DISTINCT public.group.id, public.group.name AS current_name, revision.name AS old_name 
                  FROM 
                  public.group, (
                          SELECT id, name, revision_timestamp, state, row_number() 
                          OVER(PARTITION BY id ORDER BY revision_timestamp DESC) 
                          FROM group_revision
                  ) AS revision 
                  WHERE
                  public.group.id=revision.id AND 
                  public.group.name != revision.name AND
                  public.group.state = 'active'
                  ORDER BY 
                  public.group.name;
                  '''
        log.info(_query)
        res = _db_conn.execute(_query)

        return tuple(res)

    @classmethod
    def get_redirects(cls, limit=1000):
        """
        Gets the redirects contents from the table and prepare the data in the required format
        :return: tuple (read only)
        """
        log.info("Extracting raw contents of the redirects")
        result = []
        data = model.Session.query(cls).limit(limit).all()
        for row in data:
            result.append((row.group_id, row.current_name, row.old_name))

        return tuple(result)

    @classmethod
    def get_redirects_to_view(cls, limit=1000):
        """
        This extracts all the redirects and prepare the data to the view
        :return: dict
        """
        log.info("Extracting redirects for the view")
        result = dict()
        data = model.Session.query(cls).limit(limit).all()
        try:
            last_updated = str(data[0].updated)
        except IndexError:
            last_updated = "Not available"

        for row in data:
            if row.current_name in result:
                result[row.current_name].append(row.old_name)
            else:
                result[row.current_name] = [row.old_name]

        return result, last_updated


def init_tables():
    """
    Initialise the redirects table
    :return:
    """
    Base.metadata.create_all(model.meta.engine)
